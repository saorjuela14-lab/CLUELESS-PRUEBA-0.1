-- STYLE AI MVP Supabase setup
-- Run this in the Supabase SQL editor if your tables do not already match these names/columns.

create extension if not exists "pgcrypto";

create table if not exists public."Garments" (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  type text not null,
  category text not null,
  color_primary text not null,
  brand text,
  season text,
  formality integer check (formality between 1 and 5),
  image_url text,
  created_at timestamptz not null default now()
);

create table if not exists public."Outfits" (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  occasion text not null,
  weather text,
  formality_level integer check (formality_level between 1 and 5),
  target_formality integer not null,
  outfit jsonb not null default '[]'::jsonb,
  explanation text not null,
  summary text not null,
  created_at timestamptz not null default now(),
  is_favorite boolean not null default false,
  custom_name text,
  source text not null default 'auto'
);

create table if not exists public."Chat History" (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

alter table public."Garments" enable row level security;
alter table public."Outfits" enable row level security;
alter table public."Chat History" enable row level security;

drop policy if exists "Users manage own garments" on public."Garments";
create policy "Users manage own garments"
on public."Garments"
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users manage own outfits" on public."Outfits";
create policy "Users manage own outfits"
on public."Outfits"
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users manage own chat history" on public."Chat History";
create policy "Users manage own chat history"
on public."Chat History"
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

insert into storage.buckets (id, name, public)
values ('garment-images', 'garment-images', true)
on conflict (id) do nothing;

drop policy if exists "Users upload garment images" on storage.objects;
create policy "Users upload garment images"
on storage.objects
for insert
with check (
  bucket_id = 'garment-images'
  and auth.uid()::text = (storage.foldername(name))[1]
);

drop policy if exists "Users update own garment images" on storage.objects;
create policy "Users update own garment images"
on storage.objects
for update
using (
  bucket_id = 'garment-images'
  and auth.uid()::text = (storage.foldername(name))[1]
);

drop policy if exists "Users delete own garment images" on storage.objects;
create policy "Users delete own garment images"
on storage.objects
for delete
using (
  bucket_id = 'garment-images'
  and auth.uid()::text = (storage.foldername(name))[1]
);

drop policy if exists "Public can view garment images" on storage.objects;
create policy "Public can view garment images"
on storage.objects
for select
using (bucket_id = 'garment-images');
