import os
import json
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime
import re

# ⚙️ CONFIGURACIÓN
JSON_PATH = "data/noticias.json"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RSS_URL = "https://news.google.com/rss/search?q=when:1d+geo:Mexico&hl=es-419&gl=MX&ceid=MX:es-419"

# Headers que simulan un navegador real
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

FALLBACK_IMAGE_URL = "https://images.unsplash.com/photo-1504711434269-d0385429813a?q=80&w=800&auto=format&fit=crop"

def cargar_noticias():
    if not os.path.exists(JSON_PATH): return []
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return []

def guardar_noticias(noticias):
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(noticias, f, ensure_ascii=False, indent=2)

def obtener_url_real(google_url):
    """Resuelve la redirección real. Si falla, limpia la URL."""
    try:
        # Intentamos seguir la redirección HTTP automática
        response = requests.head(google_url, headers=HEADERS, allow_redirects=True, timeout=5)
        url_final = response.url
        
        # Si la URL final sigue siendo de Google News, intentamos un método de extracción manual
        if "news.google.com" in url_final:
            res = requests.get(google_url, headers=HEADERS, timeout=5)
            # Buscamos en el meta tag 'canonical' que suele tener la URL real
            soup = BeautifulSoup(res.text, 'html.parser')
            canonical = soup.find("link", rel="canonical")
            if canonical and canonical.get("href"):
                return canonical["href"]
                
        return url_final
    except:
        return google_url

def obtener_imagen_periodico(url_real):
    """Intenta extraer la imagen de la web final."""
    # Si por error nos quedamos en Google, abortamos imagen
    if "news.google.com" in url_real:
        return FALLBACK_IMAGE_URL
        
    try:
        res = requests.get(url_real, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content, 'html.parser')
        
        # Prioridad 1: Etiquetas Meta (og:image)
        meta_img = soup.find("meta", property="og:image")
        if meta_img and meta_img.get("content"):
            return meta_img["content"]
            
        # Prioridad 2: Buscar la primera imagen grande dentro del body
        # (Esto evita logos pequeños y busca fotos de artículos)
        imgs = soup.find_all("img")
        for img in imgs:
            src = img.get("src", "")
            # Filtramos para asegurar que sea una URL completa y no un icono
            if src.startswith("http") and len(src) > 40:
                return src
    except:
        pass
    return FALLBACK_IMAGE_URL

def reescribir_con_ia(titulo_orig):
    # (Mantén tu función de IA aquí tal cual, la omito para ahorrar espacio)
    # ... asegúrate de pegar tu lógica de Groq aquí ...
    return titulo_orig, "Noticia reciente.", "Contenido del artículo."

def ejecutar():
    try:
        res = requests.get(RSS_URL, timeout=10)
        root = ET.fromstring(res.content)
    except: return

    noticias = cargar_noticias()
    for item in root.findall(".//item")[:5]: # Solo 5 para probar rápido
        t_orig = item.find("title").text
        if any(n.get('titulo_original') == t_orig for n in noticias): continue
        
        g_url = item.find("link").text
        u_real = obtener_url_real(g_url)
        
        # Si la URL resolvió a algo de Google, marcamos imagen como fallida
        if "news.google.com" in u_real:
            img = FALLBACK_IMAGE_URL
        else:
            img = obtener_imagen_periodico(u_real)
            
        t, r, c = reescribir_con_ia(t_orig)
        
        noticias.append({
            "titulo_original": t_orig,
            "titulo": t, "resumen": r, "contenido": c,
            "imagen": img, "url_origen": u_real
        })
    guardar_noticias(noticias[-20:])

if __name__ == "__main__":
    ejecutar()
