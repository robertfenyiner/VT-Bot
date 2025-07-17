import os

# ============ CONFIGURACIÓN DEL BOT TELEGRAM ======================= #
TELEGRAM_CONFIG = {
    "BOT_TOKEN": "7035976762:AAHsw2uihZuqx0VDjmw3yo9GiegTDw51DhY",  # Token del bot de Telegram
    "CHAT_ID_BOT": -1002358735347,  # ID del Grupo o Canal del chat, el bot debe ser admin 
    "SESSION_NAME": "cuenta",  # Esta es una Sesion para Mandar Archivos mas Grandes via Telethon 
    "API_ID": "9545482",  # ID de la API de Telegram, tambien para telethon... 
    "API_HASH": "ad23d323ba41bbcdddd55a0bd2fe5f3f",  # Hash de la API de Telegram, de telethon
}

# ============ CONFIGURACIÓN DE RUTAS DE EJECUCIÓN ==================== #
PATHROOT = r"C:\Bot2"  # Directorio raíz del bot.. donde se ejecuta 

# ============ CONFIGURACIÓN DE TORRENT CLIENT Y RUTAS ============== #
QBT_CONFIG = {
    "HOST": "http://127.0.0.1:8091",  # URL del servidor qBittorrent
    "USERNAME": "aliensys",  # Nombre de usuario del cliente qBittorrent
    "PASSWORD": "HExhLb@1UD^$Owcg",  # Contraseña del cliente qBittorrent
    "QBT_MOVIES": "BOT_MOVIES",  # Categoría para películas en qBittorrent (
    "QBT_SHOWS": "BOT_SHOWS",  # Categoría para series en qBittorrent
    "CREATE_TORRENT_AND_SHARE": True,  # Activar o desactivar la creación y compartición de torrents
    "TORRENTS_FILE": os.path.join(PATHROOT, "TORRENTS"),  # Directorio donde se guardarán los torrents
    "ANNOUNCE_URL": "https://privtracker.com/kzs6fq3mjag6wv8weuti5ofks8eazcdy/announce"
}

PATH_GLOBAL = {
    "MON_DOWNLS_PATH": os.path.join(PATHROOT, "VT_API", "downloads"),  # Ruta de descargas
    "VT_ROOT": os.path.join(PATHROOT, "VT_API", "pyproject.toml"),  # Ruta al archivo pyproject.toml
    "POETRY_BIN": "poetry",  # Ruta al binario de Poetry
    "ROOT_LOGS": os.path.join(PATHROOT, "Logs"),  # Ruta de los logs
    "TEMP": os.path.join(PATHROOT, "VT_API", "temp"),  # Carpera Temporal del Vinetrimer
}

# ============ OTRAS CONFIGURACIONES ===================== #
SEGUNDOS_ENTRE_COLA = 5 # Tiempo entre las colas de descarga

# ============ VALIDACIONES Y CREACIÓN DE DIRECTORIOS ===================== #
def create_directories_if_needed():
    """Crea los directorios necesarios si no existen."""
    for path in [PATH_GLOBAL["MON_DOWNLS_PATH"], PATH_GLOBAL["ROOT_LOGS"]]:
        if not os.path.exists(path):
            os.makedirs(path) 

def validate_config():
    """Valida configuraciones críticas antes de ejecutar el bot."""
    
    if not TELEGRAM_CONFIG["BOT_TOKEN"]:
        raise ValueError("El BOT_TOKEN de Telegram no está configurado.")
    if not TELEGRAM_CONFIG["API_ID"]:
        raise ValueError("El API_ID de Telegram no está configurado.")
    if not TELEGRAM_CONFIG["API_HASH"]:
        raise ValueError("El API_HASH de Telegram no está configurado.")
    if not QBT_CONFIG["HOST"]:
        raise ValueError("El HOST del cliente qBittorrent no está configurado.")
    
    create_directories_if_needed()

# Ejecutar la validación y creación de directorios al inicio
validate_config()
