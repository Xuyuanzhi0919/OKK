-- Reset default admin password to admin123 for deployments that seeded the old placeholder hash.
-- Run only if you intentionally want to restore the documented default admin credential.
UPDATE users
SET
    hashed_password = '$2b$12$XZfL2JOv0K1ytph5pt9fO.bTak9m.H6GN20KFYkd4wKoJSqK4a9ia',
    is_active = TRUE,
    is_superuser = TRUE
WHERE username = 'admin';
