# STYLE AI MVP Deploy Checklist

This version is ready to run as a browser-first MVP with Supabase.

## 1. Supabase setup

In Supabase, open the SQL editor and run:

```sql
-- backend/supabase-schema.sql
```

That creates/updates:

- `Garments`
- `Outfits`
- `Chat History`
- `garment-images` public storage bucket
- Row Level Security policies so each logged-in user only sees their own data

## 2. Auth setup

In Supabase Auth:

- Enable Email provider.
- For the fastest live demo, disable email confirmation temporarily.
- Add your deployed site URL under Auth URL configuration when you publish it.

## 3. Run locally

Open `backend/index.html` in a browser, or serve the `backend` folder with any static server.

The app now uses Supabase directly for:

- registration/login
- garment storage and retrieval
- garment image upload
- outfit history
- favorites
- chat history

## 4. Deploy online

Fast path:

- Deploy the `backend` folder as a static site on Netlify, Vercel, or Supabase Hosting.
- Set `index.html` as the main page.

No Python backend is required for this first presentation version.

## 5. Current MVP limitation

The stylist chat and outfit generation are rule-based in the browser. Real OpenAI API calls should be added through a backend or Supabase Edge Function later, because the OpenAI secret key must never be exposed in frontend code.
