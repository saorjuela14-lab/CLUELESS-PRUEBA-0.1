import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

type Garment = {
  id: string;
  type: string;
  category: string;
  color_primary: string;
  brand?: string | null;
  season?: string | null;
  formality?: number | null;
  image_url?: string | null;
};

type OutfitRequest = {
  occasion: string;
  weather?: string | null;
  formality_level?: number | null;
};

type AiOutfit = {
  garment_ids: string[];
  summary: string;
  explanation: string;
  missing_items?: string[];
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json",
    },
  });
}

function cleanText(value: unknown) {
  if (typeof value !== "string") return "";
  return value.trim();
}

function targetFormality(occasion: string, formalityLevel?: number | null) {
  if (formalityLevel && formalityLevel >= 1 && formalityLevel <= 5) return formalityLevel;

  const text = occasion.toLowerCase();

  if (text.includes("boda") || text.includes("gala") || text.includes("formal")) return 5;
  if (text.includes("oficina") || text.includes("trabajo") || text.includes("reuni")) return 4;
  if (text.includes("cena") || text.includes("cita")) return 3;
  if (text.includes("gym") || text.includes("deporte") || text.includes("playa")) return 1;

  return 3;
}

function wardrobeContext(garments: Garment[]) {
  return garments
    .slice(0, 100)
    .map((garment, index) => {
      return [
        `${index + 1}. id: ${garment.id}`,
        `type: ${garment.type}`,
        `category: ${garment.category}`,
        `color: ${garment.color_primary}`,
        garment.brand ? `brand: ${garment.brand}` : null,
        garment.season ? `season: ${garment.season}` : null,
        garment.formality ? `formality: ${garment.formality}/5` : null,
      ]
        .filter(Boolean)
        .join(", ");
    })
    .join("\n");
}

function buildPrompt(request: OutfitRequest, garments: Garment[], target: number) {
  return [
    "You are STYLE AI, an AI personal stylist.",
    "Choose an outfit using only garment IDs from the user's saved wardrobe.",
    "Prefer a complete outfit: top + bottom + footwear, or dress + footwear. Add outerwear if weather needs it, and accessory if useful.",
    "If a useful item is missing, include it in missing_items, but do not invent garment IDs.",
    "Return JSON only. No markdown. No extra text.",
    "",
    "JSON shape:",
    '{"garment_ids":["uuid"],"summary":"short Spanish summary","explanation":"Spanish explanation","missing_items":["optional missing item"]}',
    "",
    `Occasion: ${request.occasion}`,
    `Weather: ${request.weather || "not specified"}`,
    `Target formality: ${target}/5`,
    "",
    "Wardrobe:",
    wardrobeContext(garments),
  ].join("\n");
}

function parseJsonObject(text: string): AiOutfit | null {
  const trimmed = text.trim();

  try {
    return JSON.parse(trimmed) as AiOutfit;
  } catch {
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");

    if (start === -1 || end === -1 || end <= start) return null;

    try {
      return JSON.parse(trimmed.slice(start, end + 1)) as AiOutfit;
    } catch {
      return null;
    }
  }
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (request.method !== "POST") {
    return jsonResponse({ detail: "Method not allowed" }, 405);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const openAiKey = Deno.env.get("OPENAI_API_KEY");
  const openAiModel = Deno.env.get("OPENAI_MODEL") || "gpt-4.1-mini";

  if (!supabaseUrl || !supabaseAnonKey) {
    return jsonResponse({ detail: "Supabase environment variables are missing." }, 500);
  }

  if (!openAiKey) {
    return jsonResponse({ detail: "OPENAI_API_KEY is not configured." }, 500);
  }

  const authorization = request.headers.get("Authorization") || "";
  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    global: {
      headers: {
        Authorization: authorization,
      },
    },
  });

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    return jsonResponse({ detail: "User is not authenticated." }, 401);
  }

  const body = (await request.json()) as OutfitRequest;
  body.occasion = cleanText(body.occasion);
  body.weather = cleanText(body.weather) || null;
  body.formality_level = Number(body.formality_level) || null;

  if (!body.occasion) {
    return jsonResponse({ detail: "Occasion is required." }, 400);
  }

  const { data: garments, error: garmentsError } = await supabase
    .from("Garments")
    .select("id,type,category,color_primary,brand,season,formality,image_url")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });

  if (garmentsError) {
    return jsonResponse({ detail: garmentsError.message }, 500);
  }

  if (!garments || garments.length === 0) {
    return jsonResponse({ detail: "Add garments before generating an outfit." }, 400);
  }

  const target = targetFormality(body.occasion, body.formality_level);
  const prompt = buildPrompt(body, garments as Garment[], target);

  const openAiResponse = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${openAiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: openAiModel,
      input: prompt,
      temperature: 0.4,
      max_output_tokens: 550,
    }),
  });

  const openAiData = await openAiResponse.json();

  if (!openAiResponse.ok) {
    return jsonResponse(
      {
        detail: openAiData.error?.message || "OpenAI request failed.",
      },
      502,
    );
  }

  const aiOutfit = parseJsonObject(openAiData.output_text || "");

  if (!aiOutfit || !Array.isArray(aiOutfit.garment_ids)) {
    return jsonResponse({ detail: "OpenAI did not return a valid outfit." }, 502);
  }

  const garmentById = new Map((garments as Garment[]).map((garment) => [garment.id, garment]));
  const selected = aiOutfit.garment_ids
    .map((id) => garmentById.get(id))
    .filter((garment): garment is Garment => Boolean(garment));

  if (selected.length === 0) {
    return jsonResponse({ detail: "OpenAI did not select valid wardrobe items." }, 502);
  }

  const summary = cleanText(aiOutfit.summary) ||
    selected.map((garment) => `${garment.type} color ${garment.color_primary}`).join(" + ");

  const missingItems = Array.isArray(aiOutfit.missing_items)
    ? aiOutfit.missing_items.filter((item) => typeof item === "string" && item.trim())
    : [];

  const missingText = missingItems.length
    ? ` Piezas faltantes sugeridas: ${missingItems.join(", ")}.`
    : "";

  const outfitRecord = {
    user_id: user.id,
    occasion: body.occasion,
    weather: body.weather,
    formality_level: body.formality_level,
    target_formality: target,
    outfit: selected,
    explanation: `${cleanText(aiOutfit.explanation) || "Outfit generado por STYLE AI con tu armario."}${missingText}`,
    summary,
    is_favorite: false,
    custom_name: null,
    source: "ai",
  };

  const { data: savedOutfit, error: saveError } = await supabase
    .from("Outfits")
    .insert(outfitRecord)
    .select("*")
    .single();

  if (saveError) {
    return jsonResponse({ detail: saveError.message }, 500);
  }

  return jsonResponse({
    ...savedOutfit,
    model: openAiModel,
    missing_items: missingItems,
  });
});
