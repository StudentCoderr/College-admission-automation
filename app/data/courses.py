"""Default course catalogue.

This is the single source of truth used by:

* ``flask seed-courses`` (real Supabase database)
* ``scripts/demo_server.py`` (local in-memory database)
* ``sql/seed.sql`` (manual SQL setup)

Edit this list to match the institution's real programmes. Codes are unique;
re-running a seed command only inserts codes that are missing.
"""

DEFAULT_COURSES = [
    {
        "code": "BTECH-CSE",
        "name": "B.Tech Computer Science & Engineering",
        "description": "Four year undergraduate engineering programme.",
        "duration_years": 4,
        "seats_total": 120,
        "program_type": "degree",
        "eligibility": "Pass in PUC / Class 12 with Physics, Chemistry and Mathematics.",
        "tuition_fee": 85000.00,
        "eligible_qualifications": ["puc"],
    },
    {
        "code": "BTECH-ECE",
        "name": "B.Tech Electronics & Communication Engineering",
        "description": "Four year undergraduate engineering programme.",
        "duration_years": 4,
        "seats_total": 60,
        "program_type": "degree",
        "eligibility": "Pass in PUC / Class 12 with Physics, Chemistry and Mathematics.",
        "tuition_fee": 75000.00,
        "eligible_qualifications": ["puc"],
    },
    {
        "code": "BCOM",
        "name": "Bachelor of Commerce",
        "description": "Three year undergraduate commerce programme.",
        "duration_years": 3,
        "seats_total": 80,
        "program_type": "degree",
        "eligibility": "Pass in PUC / Class 12 in any stream.",
        "tuition_fee": 45000.00,
        "eligible_qualifications": ["puc"],
    },
    {
        "code": "BSC-CS",
        "name": "B.Sc Computer Science",
        "description": "Three year undergraduate science programme.",
        "duration_years": 3,
        "seats_total": 60,
        "program_type": "degree",
        "eligibility": "Pass in PUC / Class 12 with Mathematics.",
        "tuition_fee": 50000.00,
        "eligible_qualifications": ["puc"],
    },
    {
        "code": "DIP-CSE",
        "name": "Diploma in Computer Science and Engineering",
        "description": "Three year diploma in computer science and software engineering.",
        "duration_years": 3,
        "seats_total": 60,
        "program_type": "diploma",
        "eligibility": "Pass in SSLC / Class 10 with Mathematics and Science.",
        "tuition_fee": 25000.00,
        "eligible_qualifications": ["sslc"],
    },
    {
        "code": "DIP-ISE",
        "name": "Diploma in Information Science and Engineering",
        "description": "Three year diploma focused on information systems.",
        "duration_years": 3,
        "seats_total": 60,
        "program_type": "diploma",
        "eligibility": "Pass in SSLC / Class 10 with Mathematics and Science.",
        "tuition_fee": 25000.00,
        "eligible_qualifications": ["sslc"],
    },
    {
        "code": "DIP-ECE",
        "name": "Diploma in Electronics and Communication Engineering",
        "description": "Three year diploma in electronics and communication.",
        "duration_years": 3,
        "seats_total": 60,
        "program_type": "diploma",
        "eligibility": "Pass in SSLC / Class 10 with Mathematics and Science.",
        "tuition_fee": 25000.00,
        "eligible_qualifications": ["sslc"],
    },
    {
        "code": "DIP-MECH",
        "name": "Diploma in Mechanical Engineering",
        "description": "Three year diploma in mechanical systems.",
        "duration_years": 3,
        "seats_total": 60,
        "program_type": "diploma",
        "eligibility": "Pass in SSLC / Class 10 with Mathematics and Science.",
        "tuition_fee": 25000.00,
        "eligible_qualifications": ["sslc"],
    },
    {
        "code": "DIP-CIVIL",
        "name": "Diploma in Civil Engineering",
        "description": "Three year diploma in construction and civil design.",
        "duration_years": 3,
        "seats_total": 60,
        "program_type": "diploma",
        "eligibility": "Pass in SSLC / Class 10 with Mathematics and Science.",
        "tuition_fee": 25000.00,
        "eligible_qualifications": ["sslc"],
    },
    {
        "code": "DIP-COMMERCE",
        "name": "Diploma in Commercial Practice",
        "description": "Three year diploma in commerce and office practice.",
        "duration_years": 3,
        "seats_total": 80,
        "program_type": "diploma",
        "eligibility": "Pass in SSLC / Class 10.",
        "tuition_fee": 18000.00,
        "eligible_qualifications": ["sslc"],
    },
]
