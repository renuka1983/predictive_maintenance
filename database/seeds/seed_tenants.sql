-- Minimal tenant seed. For realistic data with machines, maintenance,
-- production and sensor history, use the Python generator instead:
--
--     python -m ml.data_generation.load_to_db --tenant all --reset
--
-- which also runs the maturity assessment and syncs feature toggles.

INSERT INTO tenants (id, name, slug, industry, contact_email, subscription_tier)
VALUES
    (gen_random_uuid()::text, 'Aurora Metalworks', 'tenant-a',
     'Metal Fabrication', 'ops@aurora-metalworks.example', 'level_1'),
    (gen_random_uuid()::text, 'Borealis Plastics', 'tenant-b',
     'Injection Moulding', 'maintenance@borealis-plastics.example', 'level_2'),
    (gen_random_uuid()::text, 'Cascade Foods', 'tenant-c',
     'Food Processing', 'reliability@cascade-foods.example', 'level_3')
ON CONFLICT (slug) DO NOTHING;
