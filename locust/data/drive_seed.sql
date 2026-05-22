TRUNCATE TABLE drive_folders RESTART IDENTITY CASCADE;
INSERT INTO drive_folders (id, google_folder_id, tag, created_at) VALUES (1, '1WdjkhFc41wYxU3KgirDUH6xYWDSFkDin', 'Niort', NOW());
SELECT setval(pg_get_serial_sequence('drive_folders', 'id'), coalesce(max(id), 1)) FROM drive_folders;
