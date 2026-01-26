def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = 'res_partner'
                   AND column_name = 'not_in_mod347'
                   AND data_type <> 'jsonb'
            ) THEN
                ALTER TABLE res_partner
                    ALTER COLUMN not_in_mod347
                    TYPE jsonb
                    USING to_jsonb(not_in_mod347);
            END IF;
        END$$;
        """
    )
