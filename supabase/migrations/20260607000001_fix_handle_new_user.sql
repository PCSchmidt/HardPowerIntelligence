-- Fix handle_new_user() signup trigger.
--
-- The original function (20260605000001_initial_schema.sql) referenced
-- `user_profiles` unqualified. The trigger fires as `supabase_auth_admin`, whose
-- search_path is `auth` — so the public table was not found and every sign-up
-- aborted with "Database error saving new user" (Postgres: relation
-- "user_profiles" does not exist).
--
-- Fix: schema-qualify the table and pin the function search_path to public.

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email)
    VALUES (NEW.id, NEW.email)
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;
