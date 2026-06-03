import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
import urllib.parse
import base64
import re

# ⚙️ CONFIGURACIÓN DEL BOT
MODO_TURBO = True
NOTICIAS_POR_CARRERA = 10 if MODO_TURBO else 1
RSS_URL = "https://news.google.com/rss/search?q=when:1d+geo:Mexico&hl=es-419&gl=MX&ceid=MX:es-419"
JSON_PATH = "data/noticias.json"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}

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

def decode_google_news_url(google_url):
    try:
        prefix_to_remove = "https://news.google.com/rss/articles/"
        if google_url.startswith(prefix_to_remove):
            base64_part = google_url[len(prefix_to_remove):].split('?')[0]
            base64_part += '=' * (-len(base64_part) % 4)
            url_bytes = base64.urlsafe_b64decode(base64_part)
            decoded_text = url_bytes.decode('utf-8', errors='ignore')

            url_match = re.search(r'(https?://[^\s\x1a]+)', decoded_text)
            if url_match:
                return url_match.group(1)
    except Exception as e:
        print(f"⚠️ Error decodificando URL: {e}")
        
    return google_url

def obtener_url_e_imagen_real_v3(google_url):
    url_real = decode_google_news_url(google_url)
    
    if "news.google.com" in url_real:
        try:
            res_redirect = requests.get(google_url, headers=HEADERS, timeout=10, allow_redirects=True)
            url_real = res_redirect.url
        except Exception:
            pass
            
    print(f"🔗 Fuente Real Encontrada: {url_real[:60]}...")
    
    try:
        res_articulo = requests.get(url_real, headers=HEADERS, timeout=12)
        if res_articulo.status_code == 200:
            soup = BeautifulSoup(res_articulo.content, 'html.parser')
            
            img_tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
            
            if img_tag and img_tag.get("content"):
                imagen_real = img_tag["content"]
                if imagen_real.startswith("/"):
                    imagen_real = urllib.parse.urljoin(url_real, imagen_real)
                
                print(f"✅ Imagen real encontrada: {imagen_real[:60]}...")
                return url_real, imagen_real
                
    except Exception as e:
        print(f"⚠️ Error extrayendo imagen: {e}")
        
    return url_real, FALLBACK_IMAGE_URL

def reescribir_con_ia(titulo_orig):
    if not GROQ_API_KEY:
        return titulo_orig, "Noticia importante de México.", "Revisa el enlace original para más detalles."

    # PROMPT CORREGIDO: Ya no hay variables faltantes ni texto para rellenar
    prompt = f"""Eres un periodista profesional mexicano. A partir del siguiente titular de noticia, genera un artículo periodístico completo en español.
    
    TITULAR: {titulo_orig}
    
    Responde ÚNICAMENTE con un objeto JSON válido con estas 3 claves exactas:
    - "titulo": Un título llamativo para la noticia.
    - "resumen": Un texto breve de dos líneas.
    - "contenido": El cuerpo de la noticia con al menos 300 palabras, estructurado de forma profesional.
    
    No agregues introducciones, conclusiones ni texto fuera de las llaves del JSON."""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 2000
    }

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", 
                          headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                          json=payload, timeout=45)
        res = r.json()
        
        if 'choices' in res:
            data = json.loads(res['choices'][0]['message']['content'])
            return data.get("titulo", titulo_orig), data.get("resumen", "Noticia importante."), data.get("contenido", "Detalles en el enlace.")
        else:
            print(f"⚠️ Error IA: La API no devolvió texto. Usando originales.")
            return titulo_orig, "Noticia disponible en el enlace.", "Revisa el enlace original."

    except Exception as e:
        print(f"⚠️ Error IA: {e}")
        return titulo_orig, "Noticia disponible en el enlace.", "Revisa el enlace original."

def ejecutar():
    try:
        res = requests.get(RSS_URL, timeout=10)
        root = ET.fromstring(res.content)
    except Exception as e:
        print(f"❌ Error RSS: {e}")
        return

    noticias_guardadas = cargar_noticias()
    nuevos = 0

    for item in root.findall(".//item")[:NOTICIAS_POR_CARRERA]:
        t_orig = item.find("title").text
        google_url = item.find("link").text if item.find("link") is not None else "#"

        if any(n.get('titulo_original') == t_orig for n in noticias_guardadas):
            continue

        print(f"🔄 Procesando: {t_orig[:60]}...")
        
        t_ia, r_ia, c_ia = reescribir_con_ia(t_orig)
        url_real, img_url = obtener_url_e_imagen_real_v3(google_url)

        nuevo_id = max([n.get("id", 0) for n in noticias_guardadas], default=0) + 1
        noticias_guardadas.append({
            "id": nuevo_id,
            "titulo_original": t_orig,
            "titulo": t_ia,
            "resumen": r_ia,
            "contenido": c_ia,
            "imagen": img_url,
            "fecha": datetime.today().strftime('%Y-%m-%d'),
            "url_origen": url_real
        })
        nuevos += 1
        print(f"✅ Noticia '{t_orig[:20]}...' guardada con éxito.")

    if nuevos > 0:
        guardar_noticias(noticias_guardadas[-100:])
        print(f"💾 Guardadas {nuevos} noticias nuevas.")
    else:
        print("ℹ️ No hay noticias nuevas.")

if __name__ == "__main__":
    ejecutar()
