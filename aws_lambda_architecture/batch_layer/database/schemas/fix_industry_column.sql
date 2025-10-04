-- Fix VARCHAR(50) constraint on industry column
-- Run this in your AWS RDS PostgreSQL database to allow longer industry names

ALTER TABLE symbol_metadata 
ALTER COLUMN industry TYPE VARCHAR(255);

-- Verify the change
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'symbol_metadata' AND column_name = 'industry';


