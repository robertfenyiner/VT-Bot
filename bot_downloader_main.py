import os
import sys
import asyncio
import subprocess
import threading
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import deque, defaultdict
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import logging
import shutil
from pymediainfo import MediaInfo
from colorama import init, Fore
sys.path.append(os.path.dirname(__file__))
import config
from func_auxiliares import (
    help_command,
    ping_test,
    crear_inventario,
    convertir_a_mp4,
    formatear_nombre_archivo,
    extraer_informacion_video,
    enviar_archivo_telegram,
    limpiar_directorio_descargas,
    enviar_mensaje_telegram,
    calcular_tiempo_estimado,
    clean_up_temp_directory,
)
#Colores Chidos para la Consola 
init(autoreset=True)
RED = Fore.RED
GREEN = Fore.GREEN
YELLOW = Fore.YELLOW
CYAN = Fore.CYAN
RESET = Fore.RESET
MAGENTA = Fore.MAGENTA

#Configuracion de Logger (Innecesario por cierto, solo guarda errores) 
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_log.txt"), 
        logging.StreamHandler()            
    ],
)

# Variables globales
BOT_TOKEN = config.TELEGRAM_CONFIG["BOT_TOKEN"]
SEGUNDOS_ENTRE_COLA = config.SEGUNDOS_ENTRE_COLA
EXTENSIONES = [".mkv", ".mka", ".mks"]
MON_DOWNLS_PATH = config.PATH_GLOBAL["MON_DOWNLS_PATH"]

# Inventario inicial
INVENTARIO_DESCARGAS = set()  # Conjunto vacío para almacenar archivos descargados
# Clase del Bot de Telegram
class TelegramBot(threading.Thread):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.lista_trabajos = deque()
        self.lock = threading.Lock()
        self.trabajo_actual = None
        self.intentos_fallidos = defaultdict(int)  # Inicializar intentos fallidos

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Responde con el estado de la cola."""
        with self.lock:
            trabajos_pendientes = list(self.lista_trabajos)
            trabajo_en_curso = self.trabajo_actual

        respuesta = "🥊 **Estado de la cola:**\n"
        if trabajo_en_curso:
            respuesta += f"😈 Trabajo en curso: `/{trabajo_en_curso[0]} {trabajo_en_curso[1]}`\n"
        else:
            respuesta += "🟢 No hay trabajos en curso.\n"

        if trabajos_pendientes:
            respuesta += "📋 **Trabajos pendientes:**\n"
            for trabajo in trabajos_pendientes:
                # Asegurarse de que cada trabajo es una tupla con 3 elementos
                if len(trabajo) == 3:  # (tipo, argumentos, mensaje)
                    tipo, argumentos, _ = trabajo
                    respuesta += f"- `{tipo} {argumentos}`\n"
                else:
                    # Si no es una tupla válida, indicarlo en el log y continuar
                    logging.warning(f"Elemento no válido en la cola: {trabajo}")
                    respuesta += f"- **Elemento inválido en la cola: {trabajo}**\n"
        else:
            respuesta += "✅ No hay trabajos pendientes en la cola."

        await update.message.reply_text(respuesta, parse_mode="Markdown")

    async def cancel_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela todos los trabajos pendientes en la cola."""
        with self.lock:
            trabajos_cancelados = len(self.lista_trabajos)
            self.lista_trabajos.clear()
        await update.message.reply_text(f"🚫 Se han cancelado {trabajos_cancelados} trabajos pendientes.")
    
    async def agregar_comando(self, update: Update, context: ContextTypes.DEFAULT_TYPE, tipo: str):
        """Agrega un trabajo a la cola."""
        comando = update.message.text.strip()
        if len(comando.split()) <= 1:
            await update.message.reply_text(f"⚠️ Debes especificar un argumento después de /{tipo}.")
            return

        argumentos = comando.split(maxsplit=1)[1]
        with self.lock:
            self.lista_trabajos.append((tipo, argumentos, update.message))  # Agregar el trabajo a la cola
        await update.message.reply_text(f"✅ Comando /{tipo} agregado a la cola:\n`/{tipo} {argumentos}`", parse_mode="Markdown")

    async def movie_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /movie."""
        await self.agregar_comando(update, context, "movie")

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        application = Application.builder().token(self.token).build()

        # Registro de manejadores
        application.add_handler(CommandHandler("test", ping_test))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("cola", self.status_command))
        application.add_handler(CommandHandler("cancel", self.cancel_queue))
        application.add_handler(CommandHandler("movie", self.movie_command))

        loop.run_until_complete(application.run_polling())

# Funciones de Procesamiento
def procesar_trabajo(trabajo):
    """Procesa un trabajo según su tipo."""
    tipo, argumentos, mensaje = trabajo  # Agregar el mensaje original
    print(f"Procesando trabajo: {tipo} - {argumentos}")

    try:
        if tipo == "movie":
            procesar_movie(argumentos, trabajo)
        else:
            print(f"{RED}Tipo de comando desconocido: {tipo}{RESET}")
    except Exception as e:
        logging.error(f"Error al procesar el trabajo {tipo}: {e}")

def procesar_metadata(directorio):
    """
    Recorre todos los archivos MKV y MKA en el directorio y subdirectorios,
    y actualiza la metadata de cada pista de audio y subtítulos según las reglas establecidas.
    """

    for root, _, files in os.walk(directorio):
        archivos = [f for f in files if f.endswith(('.mkv', '.mka'))]

        for archivo in archivos:
            ruta_archivo = os.path.join(root, archivo)
            print(f"\n🔍 Procesando: {ruta_archivo}")

            media_info = MediaInfo.parse(ruta_archivo)
            cambios = []
            audio_count = 0
            subtitle_count = 0

            for track in media_info.tracks:
                if track.track_type in ['Audio', 'Text']:
                    idioma = track.language.lower() if track.language else "unknown"
                    titulo = track.title if track.title else ""

                    # Asignar identificador de pista (a1, a2 para audio / s1, s2 para subtítulos)
                    if track.track_type == "Audio":
                        track_id = f'a{audio_count + 1}'
                        audio_count += 1
                    else:
                        track_id = f's{subtitle_count + 1}'
                        subtitle_count += 1

                    print(f"🎵 Track ID: {track_id}, Idioma: '{idioma}', Título: '{titulo}'")

                    # Ajustes según condiciones
                    if idioma == 'es':
                        if any(x in titulo.lower() for x in ['castellano', 'european']):
                            cambios.append((track_id, 'language', 'es-ES'))
                        else:
                            cambios.append((track_id, 'language', 'es-419'))

                    if idioma == 'pt' or 'portuguese' in titulo.lower():
                        cambios.append((track_id, 'language', 'pt-BR'))

                    if idioma in ['en', 'en-us', 'en-gb']:
                        cambios.append((track_id, 'name', 'English'))
                        if titulo.strip().lower() == 'sdh':
                            cambios.append((track_id, 'name', 'English SDH'))

            # Aplicar cambios
            if cambios:
                print(f"✅ Aplicando cambios en {ruta_archivo}...")
                for track_id, propiedad, valor in cambios:
                    comando = [
                        'mkvpropedit', ruta_archivo,
                        '--edit', f'track:{track_id}',
                        '--set', f'{propiedad}={valor}'
                    ]
                    print(f"🔧 Ejecutando: {' '.join(comando)}")
                    subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            print(f"✅ Finalizado: {ruta_archivo}")

def procesar_movie(argumentos, trabajo):
    """Maneja el comando /movie y procesa la salida."""
    try:
        # Validar argumentos
        if not argumentos.strip():
            raise ValueError("⚠️ No se proporcionaron argumentos para /movie.")

        # Valores predeterminados para las opciones
        al_opcion = "-al es-419"
        sl_opcion = "-sl es-419"
        calidad_opcion = "720p"  # Calidad predeterminada

        # Detectar si el usuario especificó un valor con -al
        al_match = re.search(r"-al\s+([^\s]+)", argumentos)
        if al_match:
            valor_al = al_match.group(1)
            al_opcion = f"-al {valor_al}"
            argumentos = re.sub(r"-al\s+[^\s]+", "", argumentos)

        # Detectar si el usuario especificó un valor con -sl
        sl_match = re.search(r"-sl\s+([^\s]+)", argumentos)
        if sl_match:
            valor_sl = sl_match.group(1)
            sl_opcion = f"-sl {valor_sl}"
            argumentos = re.sub(r"-sl\s+[^\s]+", "", argumentos)

        # Detectar si el usuario especificó un valor con -q
        q_match = re.search(r"-q\s+(\d+p?)", argumentos)
        if q_match:
            calidad_opcion = q_match.group(1)  # Extraer el valor proporcionado por el usuario
            argumentos = re.sub(r"-q\s+\d+p?", "", argumentos).strip()

        # Reconstruir los argumentos sin -al, -sl y -q
        argumentos_sin_opciones = argumentos.strip()

        # Limpiar el directorio TEMP antes de iniciar la descarga
        clean_up_temp_directory()

        # Comando de descarga (agregar las opciones de idioma, calidad y demás parámetros)
        comando_descarga = (
            f"poetry run vt dl {al_opcion} {sl_opcion} -q {calidad_opcion} -ab 128 {argumentos_sin_opciones}"
        )
        print(f"Ejecutando comando: {comando_descarga}")

        # Ejecutar el comando
        process = subprocess.run(
            comando_descarga,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(config.PATH_GLOBAL["VT_ROOT"]).parent,
        )
        if process.returncode != 0:
            raise RuntimeError(f"Error en vt dl: {process.stderr}")

        # Validar descargas
        archivos_descargados = list(Path(config.PATH_GLOBAL["MON_DOWNLS_PATH"]).iterdir())
        if not archivos_descargados:
            raise FileNotFoundError("⚠️ No se encontraron archivos descargados.")
        archivo_descargado = max(archivos_descargados, key=os.path.getctime)
        print(f"{GREEN}Archivo descargado: {archivo_descargado.name}{RESET}")

        # Verificar el tamaño del archivo descargado
        tamano_archivo = archivo_descargado.stat().st_size  # Tamaño en bytes
        limite_tamano = 3.8 * 1024**3  # 3.8 GB en bytes
        if tamano_archivo > limite_tamano:
            mensaje_error = (
                f"⚠️ El archivo descargado ({archivo_descargado.name}) tiene un tamaño de "
                f"{tamano_archivo / (1024**3):.2f} GB, lo cual excede el límite de 3.8 GB.\n"
                f"Por favor, intenta nuevamente con una resolución menor, por ejemplo:\n"
                f"`/movie -q 240`\n"
                f"El valor predeterminado es `-q 720p`. Puedes ajustarlo según sea necesario."
            )
            asyncio.run(enviar_mensaje_telegram(mensaje_error))
            return  # Terminar el procesamiento si el archivo es demasiado grande

        # Llamar a la función para modificar los metadatos del archivo descargado
        print(f"{CYAN}Modificando metadatos del archivo descargado...{RESET}")
        procesar_metadata(config.PATH_GLOBAL["MON_DOWNLS_PATH"])  # Procesar el directorio de descargas
        print(f"{GREEN}Metadatos modificados correctamente.{RESET}")

        # Procesar nuevos archivos descargados
        nuevos_archivos = crear_inventario(MON_DOWNLS_PATH, [".mkv"]) - INVENTARIO_DESCARGAS
        for archivo_mkv in nuevos_archivos:
            archivo_mp4 = archivo_mkv.with_suffix(".mp4")
            if convertir_a_mp4(archivo_mkv, archivo_mp4):
                # Calcular el tamaño del archivo y estimar el tiempo de subida
                tamano_archivo = archivo_mp4.stat().st_size  # Tamaño en bytes
                velocidad_promedio = 2 * 1024 * 1024  # Promedio de velocidad en bytes por segundo (2MB/s)
                tiempo_estimado = calcular_tiempo_estimado(tamano_archivo, velocidad_promedio)

                # Enviar mensaje con tiempo estimado al usuario
                asyncio.run(enviar_mensaje_telegram(
                    f"☕️ **¡Enviando archivo!**\n"
                    f"Relájate un momento y disfruta de una siesta... 😌\n"
                    f"⏳ **Tiempo Aproximado restante**: *{tiempo_estimado}*.\n"
                    f"¡Casi lo logramos! 🚀"
                ))
                
                print(f"{GREEN}Enviando Archivo a TL.{RESET}")
                # Enviar el archivo a Telegram
                asyncio.run(enviar_archivo_telegram(archivo_mp4))
                archivo_mkv.unlink()  # Eliminar el archivo MKV tras la conversión
        INVENTARIO_DESCARGAS.update(nuevos_archivos)  # Actualizar el inventario global

        # Limpiar el directorio de descargas
        limpiar_directorio_descargas()
    except Exception as e:
        print(f"{RED}Error procesando el trabajo: {e}{RESET}")

        
# Bucle principal para procesar trabajos y actualizar el estado de la cola
if __name__ == "__main__":
    try:
        print(f"{CYAN}Iniciando BOT de Telegram...{RESET}")
        print(f"{YELLOW}Creando inventario en: {MON_DOWNLS_PATH}{RESET}")
        INVENTARIO_DESCARGAS = crear_inventario(MON_DOWNLS_PATH, EXTENSIONES)  # Ahora devuelve un conjunto
        print(f"{GREEN}Archivos encontrados: {len(INVENTARIO_DESCARGAS)}{RESET}")

        bot_thread = TelegramBot(BOT_TOKEN)
        bot_thread.daemon = True
        bot_thread.start()

        print(f"{MAGENTA}Bot de Telegram iniciado correctamente.{RESET}")
        print(f"{CYAN}Comandos disponibles:{RESET}")
        print(f"{YELLOW}- /test\n- /help\n- /cola\n- /cancel\n- /movie\n{RESET}")

        while True:
            with bot_thread.lock:
                if not bot_thread.trabajo_actual and bot_thread.lista_trabajos:
                    bot_thread.trabajo_actual = bot_thread.lista_trabajos.popleft()  # Toma un trabajo pendiente

            if bot_thread.trabajo_actual:
                # Procesa el trabajo y espera su finalización antes de continuar
                procesar_trabajo(bot_thread.trabajo_actual)
                with bot_thread.lock:
                    bot_thread.trabajo_actual = None  # Limpia el trabajo actual después de su procesamiento

            time.sleep(SEGUNDOS_ENTRE_COLA)

    except Exception as e:
        logging.error(f"Error en el bucle principal: {e}")


