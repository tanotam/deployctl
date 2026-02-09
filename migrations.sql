CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL
);

INSERT INTO public.users (username) VALUES ('admin') ON CONFLICT DO NOTHING;