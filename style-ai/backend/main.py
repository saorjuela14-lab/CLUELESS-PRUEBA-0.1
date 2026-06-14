import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field


app = FastAPI(
    title="STYLE AI API",
    description="Backend inicial para la app STYLE AI",
    version="1.4.0",
)


# -------------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------------

DATA_FILE = Path("garments.json")
CHAT_FILE = Path("chat_history.json")
OUTFITS_FILE = Path("outfits.json")
UPLOAD_DIR = Path("uploads")

UPLOAD_DIR.mkdir(exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="uploads"
)


# -------------------------------------------------------------------
# CATEGORÍAS PERMITIDAS
# -------------------------------------------------------------------

class GarmentCategory(str, Enum):
    top = "top"
    bottom = "bottom"
    footwear = "footwear"
    outerwear = "outerwear"
    accessory = "accessory"
    dress = "dress"


# -------------------------------------------------------------------
# MODELOS DE DATOS
# -------------------------------------------------------------------

class GarmentCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    type: str
    category: GarmentCategory
    color_primary: str
    brand: Optional[str] = None
    season: Optional[str] = None
    formality: Optional[int] = Field(default=None, ge=1, le=5)
    image_url: Optional[str] = None


class GarmentUpdate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    type: Optional[str] = None
    category: Optional[GarmentCategory] = None
    color_primary: Optional[str] = None
    brand: Optional[str] = None
    season: Optional[str] = None
    formality: Optional[int] = Field(default=None, ge=1, le=5)
    image_url: Optional[str] = None


class Garment(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    type: str
    category: GarmentCategory
    color_primary: str
    brand: Optional[str] = None
    season: Optional[str] = None
    formality: Optional[int] = None
    image_url: Optional[str] = None


class OutfitRequest(BaseModel):
    occasion: str
    weather: Optional[str] = None
    formality_level: Optional[int] = Field(default=None, ge=1, le=5)


class ManualOutfitRequest(BaseModel):
    garment_ids: list[str]
    occasion: str
    weather: Optional[str] = None
    formality_level: Optional[int] = Field(default=None, ge=1, le=5)
    custom_name: Optional[str] = None


class OutfitRecord(BaseModel):
    id: str
    occasion: str
    weather: Optional[str] = None
    formality_level: Optional[int] = None
    target_formality: int
    outfit: list[Garment]
    explanation: str
    summary: str
    created_at: str
    is_favorite: bool = False
    custom_name: Optional[str] = None
    source: str = "auto"


class FavoriteUpdate(BaseModel):
    is_favorite: bool


class OutfitNameUpdate(BaseModel):
    custom_name: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    occasion: Optional[str] = None
    weather: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    content: str
    created_at: str


# -------------------------------------------------------------------
# FUNCIONES DE ARCHIVO: PRENDAS
# -------------------------------------------------------------------

def load_garments() -> list[Garment]:
    if not DATA_FILE.exists():
        return []

    with DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return [Garment(**item) for item in data]


def save_garments(garments: list[Garment]) -> None:
    data = [garment.model_dump(mode="json") for garment in garments]

    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


# -------------------------------------------------------------------
# FUNCIONES DE ARCHIVO: CHAT
# -------------------------------------------------------------------

def load_chat_history() -> list[ChatMessage]:
    if not CHAT_FILE.exists():
        return []

    with CHAT_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return [ChatMessage(**item) for item in data]


def save_chat_history(messages: list[ChatMessage]) -> None:
    data = [message.model_dump() for message in messages]

    with CHAT_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


# -------------------------------------------------------------------
# FUNCIONES DE ARCHIVO: OUTFITS
# -------------------------------------------------------------------

def load_outfits() -> list[OutfitRecord]:
    if not OUTFITS_FILE.exists():
        return []

    with OUTFITS_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return [OutfitRecord(**item) for item in data]


def save_outfits(outfits: list[OutfitRecord]) -> None:
    data = [outfit.model_dump(mode="json") for outfit in outfits]

    with OUTFITS_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


# -------------------------------------------------------------------
# FUNCIONES AUXILIARES
# -------------------------------------------------------------------

def normalize_text(value: Optional[str]) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    cleaned = str(value).strip()

    if cleaned == "":
        return None

    return cleaned


def matches_filter(value: Optional[str], search: Optional[str]) -> bool:
    if search is None:
        return True

    return normalize_text(search) in normalize_text(value)


def weather_needs_jacket(weather: Optional[str]) -> bool:
    weather_text = normalize_text(weather)

    cold_words = [
        "frío",
        "frio",
        "lluvia",
        "lluvioso",
        "invierno",
        "noche",
        "templado frío",
        "templado frio",
        "viento",
        "ventoso"
    ]

    for word in cold_words:
        if word in weather_text:
            return True

    return False


def infer_target_formality(occasion: str, formality_level: Optional[int]) -> int:
    if formality_level is not None:
        return formality_level

    occasion_text = normalize_text(occasion)

    formal_words = [
        "oficina",
        "trabajo",
        "reunión",
        "reunion",
        "formal",
        "entrevista",
        "negocios",
        "corporativo"
    ]

    elegant_words = [
        "cena",
        "cita",
        "evento",
        "elegante",
        "fiesta",
        "matrimonio",
        "boda",
        "coctel",
        "cóctel"
    ]

    casual_words = [
        "casual",
        "día",
        "dia",
        "caminar",
        "universidad",
        "relajado",
        "paseo",
        "compras"
    ]

    if any(word in occasion_text for word in formal_words):
        return 4

    if any(word in occasion_text for word in elegant_words):
        return 4

    if any(word in occasion_text for word in casual_words):
        return 2

    return 3


def garment_score(
    garment: Garment,
    target_formality: int,
    weather: Optional[str]
) -> int:
    score = 100

    if garment.formality is not None:
        score -= abs(garment.formality - target_formality) * 20
    else:
        score -= 10

    weather_text = normalize_text(weather)
    season_text = normalize_text(garment.season)

    if weather_needs_jacket(weather):
        if "invierno" in season_text or "todo" in season_text:
            score += 10

        if "verano" in season_text:
            score -= 15

    warm_words = [
        "calor",
        "soleado",
        "sol",
        "verano",
        "cálido",
        "calido",
        "caliente"
    ]

    if any(word in weather_text for word in warm_words):
        if "verano" in season_text or "todo" in season_text:
            score += 10

        if "invierno" in season_text:
            score -= 15

    return score


def find_best_by_category(
    garments: list[Garment],
    category: str,
    target_formality: int,
    weather: Optional[str]
) -> Optional[Garment]:
    candidates = []

    for garment in garments:
        if normalize_text(garment.category) == normalize_text(category):
            candidates.append(garment)

    if len(candidates) == 0:
        return None

    candidates.sort(
        key=lambda item: garment_score(item, target_formality, weather),
        reverse=True
    )

    return candidates[0]


def occasion_prefers_dress(occasion: str, target_formality: int) -> bool:
    occasion_text = normalize_text(occasion)

    dress_words = [
        "vestido",
        "boda",
        "matrimonio",
        "gala",
        "coctel",
        "cóctel",
        "fiesta",
        "evento",
        "cita",
        "cena elegante",
        "elegante"
    ]

    if any(word in occasion_text for word in dress_words):
        return True

    if target_formality >= 4:
        elegant_context = [
            "cena",
            "cita",
            "evento"
        ]

        if any(word in occasion_text for word in elegant_context):
            return True

    return False


def occasion_prefers_outerwear(
    occasion: str,
    target_formality: int,
    weather: Optional[str]
) -> bool:
    if weather_needs_jacket(weather):
        return True

    occasion_text = normalize_text(occasion)

    formal_words = [
        "oficina",
        "trabajo",
        "reunión",
        "reunion",
        "entrevista",
        "formal",
        "negocios",
        "corporativo"
    ]

    if target_formality >= 4 and any(word in occasion_text for word in formal_words):
        return True

    return False


def validate_image_file(image: UploadFile) -> str:
    if image.content_type is None:
        raise HTTPException(
            status_code=400,
            detail="No se pudo identificar el tipo de archivo"
        )

    if not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser una imagen"
        )

    original_name = image.filename or ""
    suffix = Path(original_name).suffix.lower()

    allowed_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif"
    ]

    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Formato no permitido. Usa jpg, jpeg, png, webp o gif"
        )

    return suffix


def delete_image_file_if_exists(image_url: Optional[str]) -> bool:
    if not image_url:
        return False

    file_name = Path(image_url).name

    if not file_name:
        return False

    file_path = UPLOAD_DIR / file_name

    if file_path.exists() and file_path.is_file():
        file_path.unlink()
        return True

    return False


def update_garment_image_in_outfits(garment_id: str, image_url: Optional[str]) -> None:
    """
    Actualiza la imagen de una prenda dentro de outfits guardados.
    Esto evita que historial/favoritos queden con imágenes rotas.
    """
    outfits = load_outfits()
    updated_any = False

    for outfit_index, outfit in enumerate(outfits):
        updated_garments = []
        outfit_changed = False

        for garment in outfit.outfit:
            if garment.id == garment_id:
                updated_garment = garment.model_copy(
                    update={
                        "image_url": image_url
                    }
                )
                updated_garments.append(updated_garment)
                updated_any = True
                outfit_changed = True
            else:
                updated_garments.append(garment)

        if outfit_changed:
            outfits[outfit_index] = outfit.model_copy(
                update={
                    "outfit": updated_garments
                }
            )

    if updated_any:
        save_outfits(outfits)


def build_chat_response(request: ChatRequest) -> str:
    message = normalize_text(request.message)
    garments = load_garments()

    if len(garments) == 0:
        return (
            "Todavía no tienes prendas en tu armario. "
            "Agrega al menos una prenda en /wardrobe/garments para poder ayudarte."
        )

    outfit_keywords = [
        "outfit",
        "look",
        "ponerme",
        "vestirme",
        "qué me pongo",
        "que me pongo",
        "combinar"
    ]

    if any(keyword in message for keyword in outfit_keywords):
        occasion = request.occasion or "ocasión casual"
        weather = request.weather or "clima normal"

        outfit_result = generate_outfit(
            OutfitRequest(
                occasion=occasion,
                weather=weather,
                formality_level=3
            )
        )

        summary = outfit_result.get("summary", "No pude generar resumen.")
        target_formality = outfit_result.get("target_formality", 3)

        return (
            f"Para {occasion}, te recomiendo este outfit: {summary}. "
            f"Lo elegí buscando una formalidad objetivo de {target_formality} "
            f"y considerando el clima: {weather}."
        )

    stats_keywords = [
        "armario",
        "estadísticas",
        "estadisticas",
        "tengo",
        "prendas",
        "resumen"
    ]

    if any(keyword in message for keyword in stats_keywords):
        categories = {}

        for garment in garments:
            category = str(garment.category)
            categories[category] = categories.get(category, 0) + 1

        return (
            f"Tu armario tiene {len(garments)} prendas. "
            f"Distribución por categoría: {categories}. "
            "Lo ideal es que tengas al menos top, bottom y footwear para generar buenos outfits."
        )

    category_keywords = [
        "categoría",
        "categoria",
        "categorías",
        "categorias"
    ]

    if any(keyword in message for keyword in category_keywords):
        return (
            "Las categorías válidas son: top, bottom, footwear, outerwear, accessory y dress. "
            "Ejemplo: una camisa debe ir como category='top', y unos tenis como category='footwear'."
        )

    shopping_keywords = [
        "comprar",
        "compra",
        "vale la pena",
        "precio",
        "tienda"
    ]

    if any(keyword in message for keyword in shopping_keywords):
        return (
            "Todavía no tengo conectado el módulo de compras, pero más adelante podré analizar "
            "si una prenda vale la pena según tu armario, precio y estilo."
        )

    return (
        "Soy tu estilista simple de STYLE AI. Puedes preguntarme cosas como: "
        "'¿Qué me pongo para una cena casual?', "
        "'¿Cómo está mi armario?' o "
        "'¿Qué categorías debo usar?'."
    )


# -------------------------------------------------------------------
# ENDPOINT WEB
# -------------------------------------------------------------------

@app.get("/app", include_in_schema=False)
def web_app():
    return FileResponse("index.html")


# -------------------------------------------------------------------
# ENDPOINTS BÁSICOS
# -------------------------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Bienvenido a STYLE AI",
        "status": "funcionando",
        "version": "1.4.0"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "STYLE AI API"
    }


@app.get("/styles")
def get_styles():
    return {
        "styles": [
            "casual",
            "formal",
            "business casual",
            "streetwear",
            "minimalista",
            "elegante"
        ]
    }


# -------------------------------------------------------------------
# ENDPOINTS DE ARMARIO
# -------------------------------------------------------------------

@app.get("/wardrobe/categories")
def get_categories():
    return {
        "categories": [
            {
                "value": "top",
                "description": "Parte superior: camisa, camiseta, blusa, polo, suéter"
            },
            {
                "value": "bottom",
                "description": "Parte inferior: pantalón, jean, falda, short"
            },
            {
                "value": "footwear",
                "description": "Calzado: tenis, zapatos, botas, sandalias"
            },
            {
                "value": "outerwear",
                "description": "Capa exterior: chaqueta, blazer, abrigo, hoodie"
            },
            {
                "value": "accessory",
                "description": "Accesorios: reloj, bolso, gorra, cinturón, gafas"
            },
            {
                "value": "dress",
                "description": "Vestido o enterizo"
            }
        ]
    }


@app.post("/wardrobe/garments")
def create_garment(garment: GarmentCreate):
    garments = load_garments()

    new_garment = Garment(
        id=str(uuid4()),
        type=garment.type,
        category=garment.category,
        color_primary=garment.color_primary,
        brand=garment.brand,
        season=garment.season,
        formality=garment.formality,
        image_url=garment.image_url,
    )

    garments.append(new_garment)
    save_garments(garments)

    return {
        "message": "Prenda agregada correctamente",
        "garment": new_garment
    }


@app.get("/wardrobe/garments")
def list_garments(
    category: Optional[str] = Query(default=None),
    color: Optional[str] = Query(default=None),
    season: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
):
    garments = load_garments()

    filtered_garments = []

    for garment in garments:
        if not matches_filter(garment.category, category):
            continue

        if not matches_filter(garment.color_primary, color):
            continue

        if not matches_filter(garment.season, season):
            continue

        if not matches_filter(garment.brand, brand):
            continue

        filtered_garments.append(garment)

    return {
        "total": len(filtered_garments),
        "garments": filtered_garments
    }


@app.get("/wardrobe/garments/{garment_id}")
def get_garment(garment_id: str):
    garments = load_garments()

    for garment in garments:
        if garment.id == garment_id:
            return garment

    raise HTTPException(
        status_code=404,
        detail="Prenda no encontrada"
    )


@app.put("/wardrobe/garments/{garment_id}")
def update_garment(garment_id: str, garment_update: GarmentUpdate):
    garments = load_garments()

    for index, garment in enumerate(garments):
        if garment.id == garment_id:
            update_data = garment_update.model_dump(
                exclude_unset=True,
                mode="json"
            )

            updated_garment = garment.model_copy(update=update_data)

            garments[index] = updated_garment
            save_garments(garments)

            if "image_url" in update_data:
                update_garment_image_in_outfits(
                    garment_id,
                    updated_garment.image_url
                )

            return {
                "message": "Prenda actualizada correctamente",
                "garment": updated_garment
            }

    raise HTTPException(
        status_code=404,
        detail="Prenda no encontrada"
    )


@app.post("/wardrobe/garments/{garment_id}/image")
async def upload_garment_image(
    garment_id: str,
    image: UploadFile = File(...)
):
    extension = validate_image_file(image)

    garments = load_garments()

    garment_index = None

    for index, garment in enumerate(garments):
        if garment.id == garment_id:
            garment_index = index
            break

    if garment_index is None:
        raise HTTPException(
            status_code=404,
            detail="Prenda no encontrada"
        )

    file_name = f"{garment_id}-{uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / file_name

    content = await image.read()

    max_size_mb = 5
    max_size_bytes = max_size_mb * 1024 * 1024

    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"La imagen no puede pesar más de {max_size_mb} MB"
        )

    with file_path.open("wb") as file:
        file.write(content)

    image_url = f"/uploads/{file_name}"

    current_garment = garments[garment_index]

    delete_image_file_if_exists(current_garment.image_url)

    updated_garment = current_garment.model_copy(
        update={
            "image_url": image_url
        }
    )

    garments[garment_index] = updated_garment
    save_garments(garments)

    update_garment_image_in_outfits(garment_id, image_url)

    return {
        "message": "Imagen subida correctamente",
        "image_url": image_url,
        "garment": updated_garment
    }


@app.delete("/wardrobe/garments/{garment_id}/image")
def delete_garment_image(garment_id: str):
    garments = load_garments()

    for index, garment in enumerate(garments):
        if garment.id == garment_id:
            if not garment.image_url:
                return {
                    "message": "La prenda no tenía imagen",
                    "garment": garment,
                    "file_deleted": False
                }

            file_deleted = delete_image_file_if_exists(garment.image_url)

            updated_garment = garment.model_copy(
                update={
                    "image_url": None
                }
            )

            garments[index] = updated_garment
            save_garments(garments)

            update_garment_image_in_outfits(garment_id, None)

            return {
                "message": "Imagen eliminada correctamente",
                "garment": updated_garment,
                "file_deleted": file_deleted
            }

    raise HTTPException(
        status_code=404,
        detail="Prenda no encontrada"
    )


@app.delete("/wardrobe/garments/{garment_id}")
def delete_garment(garment_id: str):
    garments = load_garments()

    for index, garment in enumerate(garments):
        if garment.id == garment_id:
            deleted = garments.pop(index)

            delete_image_file_if_exists(deleted.image_url)

            save_garments(garments)

            return {
                "message": "Prenda eliminada correctamente",
                "garment": deleted
            }

    raise HTTPException(
        status_code=404,
        detail="Prenda no encontrada"
    )


@app.get("/wardrobe/stats")
def wardrobe_stats():
    garments = load_garments()

    categories = {}
    colors = {}
    brands = {}
    seasons = {}
    with_image = 0
    without_image = 0

    for garment in garments:
        category = garment.category or "sin categoría"
        color = garment.color_primary or "sin color"
        brand = garment.brand or "sin marca"
        season = garment.season or "sin temporada"

        categories[category] = categories.get(category, 0) + 1
        colors[color] = colors.get(color, 0) + 1
        brands[brand] = brands.get(brand, 0) + 1
        seasons[season] = seasons.get(season, 0) + 1

        if garment.image_url:
            with_image += 1
        else:
            without_image += 1

    return {
        "total_garments": len(garments),
        "with_image": with_image,
        "without_image": without_image,
        "categories": categories,
        "colors": colors,
        "brands": brands,
        "seasons": seasons
    }


# -------------------------------------------------------------------
# ESTILISTA + HISTORIAL DE OUTFITS + FAVORITOS + NOMBRES
# -------------------------------------------------------------------

@app.post("/stylist/outfit")
def generate_outfit(request: OutfitRequest):
    garments = load_garments()

    if len(garments) == 0:
        raise HTTPException(
            status_code=400,
            detail="Primero debes agregar prendas a tu armario"
        )

    selected_garments = []

    target_formality = infer_target_formality(
        request.occasion,
        request.formality_level
    )

    dress = find_best_by_category(
        garments,
        "dress",
        target_formality,
        request.weather
    )

    top = find_best_by_category(
        garments,
        "top",
        target_formality,
        request.weather
    )

    bottom = find_best_by_category(
        garments,
        "bottom",
        target_formality,
        request.weather
    )

    footwear = find_best_by_category(
        garments,
        "footwear",
        target_formality,
        request.weather
    )

    outerwear = find_best_by_category(
        garments,
        "outerwear",
        target_formality,
        request.weather
    )

    accessory = find_best_by_category(
        garments,
        "accessory",
        target_formality,
        request.weather
    )

    use_dress = (
        dress is not None
        and occasion_prefers_dress(request.occasion, target_formality)
    )

    use_outerwear = occasion_prefers_outerwear(
        request.occasion,
        target_formality,
        request.weather
    )

    if use_dress:
        selected_garments.append(dress)

        if footwear:
            selected_garments.append(footwear)

        if use_outerwear and outerwear:
            selected_garments.append(outerwear)

        if accessory:
            selected_garments.append(accessory)

    else:
        if top:
            selected_garments.append(top)

        if bottom:
            selected_garments.append(bottom)

        if footwear:
            selected_garments.append(footwear)

        if use_outerwear and outerwear:
            selected_garments.append(outerwear)

        if accessory and target_formality >= 3:
            selected_garments.append(accessory)

    if len(selected_garments) == 0:
        selected_garments = garments[:3]

    outfit_description = []

    for garment in selected_garments:
        outfit_description.append(
            f"{garment.type} color {garment.color_primary}"
        )

    summary = " + ".join(outfit_description)

    explanation = (
        "Este outfit fue generado seleccionando prendas por categoría, "
        "priorizando formalidad cercana al evento, temporada compatible con el clima "
        "y evitando usar vestido a menos que la ocasión lo justifique."
    )

    outfit_record = OutfitRecord(
        id=str(uuid4()),
        occasion=request.occasion,
        weather=request.weather,
        formality_level=request.formality_level,
        target_formality=target_formality,
        outfit=selected_garments,
        explanation=explanation,
        summary=summary,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_favorite=False,
        custom_name=None,
        source="auto"
    )

    outfits = load_outfits()
    outfits.append(outfit_record)
    save_outfits(outfits)

    return {
        "id": outfit_record.id,
        "occasion": outfit_record.occasion,
        "weather": outfit_record.weather,
        "formality_level": outfit_record.formality_level,
        "target_formality": outfit_record.target_formality,
        "outfit": outfit_record.outfit,
        "explanation": outfit_record.explanation,
        "summary": outfit_record.summary,
        "created_at": outfit_record.created_at,
        "is_favorite": outfit_record.is_favorite,
        "custom_name": outfit_record.custom_name,
        "source": outfit_record.source
    }


@app.post("/stylist/outfits/manual")
def create_manual_outfit(request: ManualOutfitRequest):
    garments = load_garments()

    if len(garments) == 0:
        raise HTTPException(
            status_code=400,
            detail="Primero debes agregar prendas a tu armario"
        )

    if not request.garment_ids or len(request.garment_ids) == 0:
        raise HTTPException(
            status_code=400,
            detail="Debes seleccionar al menos una prenda"
        )

    if normalize_text(request.occasion) == "":
        raise HTTPException(
            status_code=400,
            detail="Debes escribir una ocasión"
        )

    garment_by_id = {}

    for garment in garments:
        garment_by_id[garment.id] = garment

    selected_garments = []
    missing_ids = []
    used_ids = set()

    for garment_id in request.garment_ids:
        if garment_id in used_ids:
            continue

        used_ids.add(garment_id)

        garment = garment_by_id.get(garment_id)

        if garment is None:
            missing_ids.append(garment_id)
        else:
            selected_garments.append(garment)

    if len(missing_ids) > 0:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Una o más prendas no existen",
                "missing_ids": missing_ids
            }
        )

    if len(selected_garments) == 0:
        raise HTTPException(
            status_code=400,
            detail="No se pudo crear el outfit porque no hay prendas válidas seleccionadas"
        )

    target_formality = infer_target_formality(
        request.occasion,
        request.formality_level
    )

    outfit_description = []

    for garment in selected_garments:
        outfit_description.append(
            f"{garment.type} color {garment.color_primary}"
        )

    summary = " + ".join(outfit_description)

    custom_name = clean_optional_text(request.custom_name)

    explanation = (
        "Este outfit fue creado manualmente seleccionando prendas del armario. "
        f"Formalidad objetivo: {target_formality}. "
        f"Ocasión: {request.occasion}."
    )

    if request.weather:
        explanation += f" Clima considerado: {request.weather}."

    outfit_record = OutfitRecord(
        id=str(uuid4()),
        occasion=request.occasion,
        weather=request.weather,
        formality_level=request.formality_level,
        target_formality=target_formality,
        outfit=selected_garments,
        explanation=explanation,
        summary=summary,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_favorite=False,
        custom_name=custom_name,
        source="manual"
    )

    outfits = load_outfits()
    outfits.append(outfit_record)
    save_outfits(outfits)

    return {
        "id": outfit_record.id,
        "occasion": outfit_record.occasion,
        "weather": outfit_record.weather,
        "formality_level": outfit_record.formality_level,
        "target_formality": outfit_record.target_formality,
        "outfit": outfit_record.outfit,
        "explanation": outfit_record.explanation,
        "summary": outfit_record.summary,
        "created_at": outfit_record.created_at,
        "is_favorite": outfit_record.is_favorite,
        "custom_name": outfit_record.custom_name,
        "source": outfit_record.source
    }


@app.get("/stylist/outfits")
def get_outfit_history():
    outfits = load_outfits()

    return {
        "total": len(outfits),
        "outfits": list(reversed(outfits))
    }


@app.get("/stylist/outfits/favorites")
def get_favorite_outfits():
    outfits = load_outfits()

    favorites = []

    for outfit in outfits:
        if outfit.is_favorite:
            favorites.append(outfit)

    return {
        "total": len(favorites),
        "outfits": list(reversed(favorites))
    }


@app.put("/stylist/outfits/{outfit_id}/favorite")
def update_outfit_favorite(outfit_id: str, favorite_update: FavoriteUpdate):
    outfits = load_outfits()

    for index, outfit in enumerate(outfits):
        if outfit.id == outfit_id:
            updated_outfit = outfit.model_copy(
                update={
                    "is_favorite": favorite_update.is_favorite
                }
            )

            outfits[index] = updated_outfit
            save_outfits(outfits)

            if favorite_update.is_favorite:
                message = "Outfit marcado como favorito"
            else:
                message = "Outfit quitado de favoritos"

            return {
                "message": message,
                "outfit": updated_outfit
            }

    raise HTTPException(
        status_code=404,
        detail="Outfit no encontrado"
    )


@app.put("/stylist/outfits/{outfit_id}/name")
def update_outfit_name(outfit_id: str, name_update: OutfitNameUpdate):
    """
    Actualiza el nombre personalizado de un outfit.

    Si custom_name viene vacío, se borra el nombre personalizado.
    """
    outfits = load_outfits()

    new_name = clean_optional_text(name_update.custom_name)

    for index, outfit in enumerate(outfits):
        if outfit.id == outfit_id:
            updated_outfit = outfit.model_copy(
                update={
                    "custom_name": new_name
                }
            )

            outfits[index] = updated_outfit
            save_outfits(outfits)

            if new_name:
                message = "Nombre personalizado actualizado"
            else:
                message = "Nombre personalizado eliminado"

            return {
                "message": message,
                "outfit": updated_outfit
            }

    raise HTTPException(
        status_code=404,
        detail="Outfit no encontrado"
    )


@app.delete("/stylist/outfits/history")
def clear_outfit_history():
    save_outfits([])

    return {
        "message": "Historial de outfits eliminado correctamente"
    }


# -------------------------------------------------------------------
# CHAT DE ESTILISTA SIMPLE
# -------------------------------------------------------------------

@app.post("/stylist/chat")
def stylist_chat(request: ChatRequest):
    history = load_chat_history()

    user_message = ChatMessage(
        role="user",
        content=request.message,
        created_at=datetime.now(timezone.utc).isoformat()
    )

    assistant_content = build_chat_response(request)

    assistant_message = ChatMessage(
        role="assistant",
        content=assistant_content,
        created_at=datetime.now(timezone.utc).isoformat()
    )

    history.append(user_message)
    history.append(assistant_message)

    save_chat_history(history)

    return {
        "reply": assistant_content,
        "last_messages": history[-10:]
    }


@app.get("/stylist/chat/history")
def get_chat_history():
    history = load_chat_history()

    return {
        "total": len(history),
        "messages": history
    }


@app.delete("/stylist/chat/history")
def clear_chat_history():
    save_chat_history([])

    return {
        "message": "Historial del chat eliminado correctamente"
    }