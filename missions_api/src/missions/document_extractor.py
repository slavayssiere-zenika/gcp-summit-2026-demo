import logging
import io
import re
import httpx
from google.genai import types

try:
    import docx
except ImportError:
    docx = None

logger = logging.getLogger(__name__)

async def extract_document_contents(url: str, file_bytes: bytes, file_mime: str, description: str, headers: dict, http_client: httpx.AsyncClient) -> tuple[list, str]:
    """
    Extrait et prépare les contenus depuis une URL, un document DOCX ou un fichier binaire (PDF/TXT)
    pour l'ingestion multimodale Gemini.
    Retourne la liste des 'contents' à ajouter au prompt Gemini et la description finale.
    """
    gemini_contents = []
    final_description = description or ""

    if url and not file_bytes:
        # URL transform
        if "docs.google.com/document/d/" in url:
            doc_id = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
            if doc_id:
                fetch_url = f"https://docs.google.com/document/d/{doc_id.group(1)}/export?format=txt"
            else:
                fetch_url = url
        else:
            fetch_url = url
            
        req_heads = headers.copy()
        doc_res = await http_client.get(fetch_url, headers=req_heads, follow_redirects=True)
        if doc_res.status_code == 200:
            gemini_contents.append(f"Mission Text Document from URL: \n{doc_res.text}")
            if not final_description:
                final_description = f"Document chargé depuis: {url}"
        else:
            logger.warning(f"Failed to fetch document at {fetch_url}, status: {doc_res.status_code}")

    if file_bytes:
        DOCX_MIME_TYPES = {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }
        if file_mime in DOCX_MIME_TYPES:
            # Gemini ne supporte pas les fichiers Word en natif.
            # On extrait le texte brut via python-docx et on l'injecte comme contenu texte.
            if docx is None:
                raise RuntimeError("python-docx is not installed, cannot process DOCX files")
                
            try:
                doc = docx.Document(io.BytesIO(file_bytes))
                docx_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                if docx_text:
                    gemini_contents.append(f"Contenu du document Word :\n{docx_text}")
                else:
                    logger.warning("Le fichier DOCX ne contient aucun texte extractible.")
            except Exception as e:
                logger.error(f"Erreur d'extraction DOCX: {str(e)}")
                raise
        else:
            try:
                # Ingestion multimodale directe via Gemini (Native OCR) pour les PDF et TXT
                part = types.Part.from_bytes(data=file_bytes, mime_type=file_mime)
                gemini_contents.append(part)
            except Exception as e:
                logger.error(f"Erreur d'ingestion binaire Gemini: {str(e)}")
                raise

        if not final_description:
            final_description = "Mission chargée via document binaire et processée nativement par Gemini."

    if final_description and not file_bytes and not url:
        gemini_contents.append(f"Description fournie: {final_description}")

    return gemini_contents, final_description
