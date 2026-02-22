-- Allow country to be empty (for free-question leads)
ALTER TABLE leads ALTER COLUMN country SET DEFAULT '';
ALTER TABLE leads ALTER COLUMN country DROP NOT NULL;
