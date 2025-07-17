import os
import sys
from telegram import Update
from telegram.ext import ContextTypes
import logging
from colorama import Fore, init
import re
from pathlib import Path
from telegram.helpers import escape_markdown
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
from colorama import Fore
from telethon import TelegramClient
import tempfile
from pymediainfo import MediaInfo
import qbittorrentapi
from qbittorrentapi import Client, TaskStatus
import time
import config
import requests
import shutil
import random
import string
import subprocess
import asyncio
from datetime import timedelta
from PIL import Image
import io

# Inicialización de colores
init(autoreset=True)
RED = Fore.RED
GREEN = Fore.GREEN
YELLOW = Fore.YELLOW
CYAN = Fore.CYAN
RESET = Fore.RESET
MAGENTA = Fore.MAGENTA

# Variables de Telegram desde config.py
API_ID = config.TELEGRAM_CONFIG["API_ID"]
API_HASH = config.TELEGRAM_CONFIG["API_HASH"]
SESSION_NAME = config.TELEGRAM_CONFIG["SESSION_NAME"]
CHAT_ID_BOT = config.TELEGRAM_CONFIG["CHAT_ID_BOT"]

# Configuración de qBittorrent
HOST = config.QBT_CONFIG["HOST"]
USERNAME = config.QBT_CONFIG["USERNAME"]
PASSWORD = config.QBT_CONFIG["PASSWORD"]
CREATE_TORRENT_AND_SHARE = config.QBT_CONFIG["CREATE_TORRENT_AND_SHARE"]
TORRENTS_FILE = config.QBT_CONFIG["TORRENTS_FILE"]
#ANNOUNCE_URL = config.QBT_CONFIG["ANNOUNCE_URL"]

# Rutas y otras configuraciones
MON_DOWNLS_PATH = config.PATH_GLOBAL["MON_DOWNLS_PATH"]
TEMP = config.PATH_GLOBAL["TEMP"]

#Help general del Bot... 
async def ping_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica si el bot está disponible."""
    logging.info(f"{GREEN}Ping test recibido.")
    await update.message.reply_text("✅ Bot disponible para recibir comandos.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 **Comandos Disponibles:**\n"
        "/ping - Verificar si el bot está activo.\n"
        "/help - Mostrar este menú de ayuda.\n"
        "/cola - Listar trabajos pendientes.\n"
        "/movie Service URL - Agregar un trabajo para procesar un archivo MKV.\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

def crear_inventario(ruta, extensiones):
    """
    Crea un inventario inicial de archivos en una carpeta monitoreada.
    Args:
        ruta (str): Ruta del directorio a escanear.
        extensiones (list): Extensiones de archivos a incluir (ej: ['.mkv', '.mka', '.mks']).
    Returns:
        set: Conjunto de rutas absolutas de archivos relevantes.
    """
    # Validar la ruta
    directorio = Path(ruta)
    if not directorio.exists() or not directorio.is_dir():
        logging.warning(f"La ruta especificada no existe o no es un directorio: {ruta}")
        return set()
    
    # Normalizar extensiones
    extensiones = [ext.lower().strip() for ext in extensiones]
    logging.info(f"Creando inventario en {ruta} con extensiones: {extensiones}")
    
    # Generar inventario de archivos
    archivos = {
        archivo for archivo in directorio.rglob("*") 
        if archivo.is_file() and archivo.suffix.lower() in extensiones
    }
    
    logging.info(f"Inventario creado: {len(archivos)} archivos encontrados.")
    return archivos
    
def convertir_a_mp4(input_path: Path, output_path: Path) -> bool:
    """
    Convierte un archivo MKV a MP4 cambiando solo el contenedor.
    :param input_path: Ruta del archivo MKV de entrada.
    :param output_path: Ruta del archivo MP4 de salida.
    :return: True si la conversión fue exitosa, False en caso contrario.
    """
    try:
        comando = [
            "ffmpeg",
            "-i", str(input_path),           # Archivo de entrada
            "-map", "0",                     # Mapear todos los streams
            "-map", "-0:s:m:forced",         # Excluir subtítulos forzados
            "-c:v", "copy",                  # Copiar el stream de video sin recodificar
            "-c:a", "copy",                  # Copiar el stream de audio sin recodificar
            "-c:s", "mov_text",              # Convertir subtítulos a formato compatible con MP4
            # "-vf", "scale=1280:720",         # Forzar resolución 16:9
            str(output_path)                 # Archivo de salida
        ]
        print(f"{CYAN}Ejecutando: {' '.join(comando)}{RESET}")
        subprocess.run(comando, check=True)
        print(f"{GREEN}Conversión exitosa: {output_path}{RESET}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"{RED}Error al convertir el archivo: {e}{RESET}")
        return False
        
def formatear_nombre_archivo(nombre_archivo):
    """Formatea el nombre del archivo para usarlo como título en Telegram."""
    nombre_sin_ext = Path(nombre_archivo).stem
    nombre_limpio = re.sub(r"[._-]+", " ", nombre_sin_ext)
    match_anio = re.search(r"(\b19[0-9]{2}\b|\b20[0-9]{2}\b)", nombre_limpio)
    if match_anio:
        anio = match_anio.group(0)
        titulo = nombre_limpio[:match_anio.start()].strip()
        return f"{titulo} ({anio})"
    return nombre_limpio.strip().title()

def extraer_informacion_video(file_path):
    """Extrae información básica del video usando pymediainfo."""
    try:
        media_info = MediaInfo.parse(file_path)
        for track in media_info.tracks:
            if track.track_type == "Video":
                return {
                    "width": track.width,
                    "height": track.height,
                    "duration": track.duration // 1000 if track.duration else 0
                }
    except Exception as e:
        print(f"{RED}Error extrayendo información del video: {e}{RESET}")
    return {}

def extraer_miniatura(video_path: Path, thumbnail_path: Path):
    """
    Extrae una miniatura del video usando FFmpeg.
    :param video_path: Ruta del archivo de video.
    :param thumbnail_path: Ruta donde se guardará la miniatura.
    """
    try:
        comando = [
            "ffmpeg",
            "-i", str(video_path),
            "-ss", "00:00:01",  # Captura un frame en el segundo 1
            "-vframes", "1",   # Solo extraer un frame
            "-q:v", "1",       # Calidad de la miniatura (2 es alta calidad)
            str(thumbnail_path)
        ]
        subprocess.run(comando, check=True)
        print(f"{GREEN}Miniatura extraída: {thumbnail_path}{RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}Error al extraer miniatura: {e}{RESET}")

def redimensionar_miniatura(ruta_miniatura: Path, max_dimensiones=(200, 200), formato="JPEG", calidad=85):
    """
    Redimensiona una imagen para cumplir con los requisitos de Telegram.
    :param ruta_miniatura: Ruta de la imagen original.
    :param max_dimensiones: Dimensiones máximas permitidas (ancho, alto).
    :param formato: Formato de salida (JPEG por defecto).
    :param calidad: Calidad de compresión (85 por defecto).
    :return: BytesIO con la imagen redimensionada.
    """
    try:
        with Image.open(ruta_miniatura) as img:
            # Redimensionar manteniendo la proporción
            img.thumbnail(max_dimensiones)
            
            # Convertir a RGB si la imagen tiene un canal alfa
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # Guardar en un buffer en memoria
            buffer = io.BytesIO()
            img.save(buffer, format=formato, quality=calidad)
            buffer.seek(0)
            return buffer
    except Exception as e:
        print(f"{RED}Error al redimensionar miniatura: {e}{RESET}")
        return None
               
async def enviar_archivo_telegram(archivo_path: Path):
    """
    Envía un archivo MP4 a Telegram con una miniatura estática redimensionada usando Telethon.
    """
    try:
        if archivo_path.is_file():
            # Extraer información del video
            info_video = extraer_informacion_video(archivo_path)
            nombre_formateado = formatear_nombre_archivo(archivo_path.name)
            resolucion = f"{info_video.get('width', 'N/A')}x{info_video.get('height', 'N/A')}"
            
            # Crear el mensaje con la información del video
            mensaje_info = (
                f"✅✅ {nombre_formateado} ✅✅\n"
                f"🎬 Resolución: {resolucion}\n"
                f"⏰ Duración: {str(timedelta(seconds=info_video.get('duration', 0)))}\n"
            )

            # Verificar que la miniatura estática exista
            # if not THUMBNAIL_PATH.exists():
                # raise FileNotFoundError(f"Miniatura estática no encontrada: {THUMBNAIL_PATH}")

            # Redimensionar la miniatura estática
            # miniatura_redimensionada = redimensionar_miniatura(THUMBNAIL_PATH)
            # if not miniatura_redimensionada:
                # raise ValueError("No se pudo redimensionar la miniatura estática.")

            # Enviar el archivo con la miniatura estática redimensionada
            async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
                await client.send_file(
                    CHAT_ID_BOT,
                    archivo_path,
                    supports_streaming=True
                )
                print(f"{GREEN}Archivo enviado: {archivo_path.name}{RESET}")

                # Enviar el mensaje con la información del video
                await client.send_message(
                    CHAT_ID_BOT,
                    mensaje_info
                )
                print(f"{GREEN}Mensaje de información enviado: {mensaje_info}{RESET}")
        else:
            print(f"{RED}Archivo no encontrado: {archivo_path}{RESET}")
    except Exception as e:
        print(f"{RED}Error al enviar archivo: {e}{RESET}")
      
def limpiar_directorio_descargas():
    """Limpia el directorio de descargas."""
    try:
        for archivo in Path(MON_DOWNLS_PATH).iterdir():
            if archivo.is_file():
                archivo.unlink()
            elif archivo.is_dir():
                shutil.rmtree(archivo)
        print(f"{GREEN}Directorio de descargas limpiado.{RESET}")
    except Exception as e:
        print(f"{RED}Error al limpiar el directorio: {e}{RESET}")

async def enviar_mensaje_telegram(mensaje: str):
    """Envía un mensaje de texto a Telegram."""
    try:
        async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
            await client.send_message(CHAT_ID_BOT, mensaje)
            print(f"Mensaje enviado: {mensaje}")
    except Exception as e:
        print(f"{RED}Error al enviar mensaje: {e}{RESET}")
        
def calcular_tiempo_estimado(tamano_archivo: int, velocidad_promedio: int) -> str:
    """
    Calcula el tiempo estimado de subida en formato legible.
    :param tamano_archivo: Tamaño del archivo en bytes.
    :param velocidad_promedio: Velocidad promedio de subida en bytes por segundo.
    :return: Tiempo estimado en formato legible (ejemplo: "5 minutos").
    """
    if velocidad_promedio <= 0:
        return "Desconocido"
    tiempo_segundos = tamano_archivo / velocidad_promedio
    if tiempo_segundos < 60:
        return f"{int(tiempo_segundos)} segundos"
    elif tiempo_segundos < 3600:
        minutos = tiempo_segundos / 60
        return f"{int(minutos)} minutos"
    else:
        horas = tiempo_segundos / 3600
        return f"{int(horas)} horas"

def clean_up_temp_directory():
    """
    Limpia el directorio TEMP si no está vacío.
    """
    try:
        temp_path = Path(config.PATH_GLOBAL["TEMP"])
        if temp_path.exists():
            # Verificar si el directorio TEMP contiene archivos
            archivos_en_temp = list(temp_path.iterdir())
            if archivos_en_temp:
                print(f"{YELLOW}Limpiando directorio TEMP...{RESET}")
                for archivo in archivos_en_temp:
                    if archivo.is_file():
                        archivo.unlink()  # Eliminar archivos
                    elif archivo.is_dir():
                        shutil.rmtree(archivo)  # Eliminar subdirectorios
                print(f"{GREEN}Directorio TEMP limpiado correctamente.{RESET}")
            else:
                print(f"{CYAN}El directorio TEMP ya está vacío.{RESET}")
        else:
            print(f"{CYAN}El directorio TEMP no existe. Creándolo...{RESET}")
            temp_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        mensaje_error = f"⚠️ Error al limpiar el directorio TEMP: {e}"
        logging.error(mensaje_error)
        print(f"{RED}{mensaje_error}{RESET}")