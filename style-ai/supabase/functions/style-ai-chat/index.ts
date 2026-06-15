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
};

type ChatRequest = {
  message: string;
  occasion?: string | null;
  weather?: string | null;
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

function wardrobeContext(garments: Garment[]) {
  if (garments.length === 0) {
    return "The user has no garments saved yet.";
  }

  return garments
    .slice(0, 80)
    .map((garment, index) => {
      return [
        `${index + 1}. ${garment.type}`,
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

function buildPrompt(request: ChatRequest, garments: Garment[]) {
  return [
    "You are STYLE AI, a warm, practical personal stylist.",
    "Use only the user's saved wardrobe when recommending specific owned items.",
    "If the wardrobe lacks an item, say it is a missing piece instead of pretending the user owns it.",
    "Answer in Spanish unless the user clearly writes in another language.",
    "Keep the response concise, specific, and presentation-ready.",
    "",
    `Occasion: ${request.occasion || "not specified"}`,
    `Weather: ${request.weather || "not specified"}`,
    "",
    "Saved wardrobe:",
    wardrobeContext(garments),
    "",
    "User message:",
    request.message,
  ].join("\n");
}

Deno.serve(async (request) => {
  console.log("STYLE AI CHAT START");
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

  const requestBody = (await request.json()) as ChatRequest;
  requestBody.message = cleanText(requestBody.message);
  requestBody.occasion = cleanText(requestBody.occasion) || null;
  requestBody.weather = cleanText(requestBody.weather) || null;

  if (!requestBody.message) {
    return jsonResponse({ detail: "Message is required." }, 400);
  }

  const { data: garments, error: garmentsError } = await supabase
    .from("Garments")
    .select("id,type,category,color_primary,brand,season,formality")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });

  if (garmentsError) {
    return jsonResponse({ detail: garmentsError.message }, 500);
  }

  const prompt = buildPrompt(requestBody, (garments || []) as Garment[]);

  const openAiResponse = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${openAiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: openAiModel,
      input: prompt,
      temperature: 0.7,
      max_output_tokens: 450,
    }),
  });

  const openAiData = await openAiResponse.json();

console.log("OPENAI STATUS:", openAiResponse.status);
console.log("OPENAI RESPONSE:", JSON.stringify(openAiData));

if (!openAiResponse.ok) {
  return jsonResponse(
    {
      detail: openAiData?.error?.message || "OpenAI request failed.",
      openai_response: openAiData,
    },
    502,
  );
}

const reply = cleanText(
  openAiData?.output_text ||
  openAiData?.output?.[0]?.content?.[0]?.text ||
  ""
);

console.log("PARSED REPLY:", reply);

if (!reply) {
  return jsonResponse(
    {
      detail: "OpenAI returned an empty response.",
      openai_response: openAiData,
    },
    502,
  );
}
  const { error: insertError } = await supabase.from("Chat History").insert([
    {
      user_id: user.id,
      role: "user",
      content: requestBody.message,
    },
    {
      user_id: user.id,
      role: "assistant",
      content: reply,
    },
  ]);

  if (insertError) {
    return jsonResponse({ detail: insertError.message }, 500);
  }

  const { data: messages, error: historyError } = await supabase
    .from("Chat History")
    .select("role,content,created_at")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(10);

  if (historyError) {
    return jsonResponse({ detail: historyError.message }, 500);
  }

  return jsonResponse({
    reply,
    model: openAiModel,
    wardrobe_count: garments?.length || 0,
    last_messages: (messages || []).reverse(),
  });
});
