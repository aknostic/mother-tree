-- Bootstrap helper functions that schema.sql references before defining them.
-- Runs before schema.sql (alphabetical order in docker-entrypoint-initdb.d).
-- Not used by CNPG, which loads schema.sql directly via postInitTemplateSQL.

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
