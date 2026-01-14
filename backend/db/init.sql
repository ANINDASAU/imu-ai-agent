-- Run this in your Supabase SQL editor to create the table
create table if not exists public.student_queries (
  id bigserial primary key,
  student_name text not null,
  academic_year text not null,
  student_query text not null,
  routed_unit text not null,
  timestamp timestamptz not null default now()
);

create index if not exists idx_student_queries_timestamp on public.student_queries (timestamp);
