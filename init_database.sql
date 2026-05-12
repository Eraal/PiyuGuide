BEGIN;

-- ==========================================
-- 1. CAMPUS DATA
-- ==========================================
INSERT INTO campuses (name, code, address, description, campus_theme_key, is_active)
VALUES (
    'Laguna State Polytechnic University - Siniloan Host Campus',
    'LSPU-SHC',
    'Siniloan, Laguna',
    'Host Campus of Laguna State Polytechnic University',
    'blue',
    TRUE
) ON CONFLICT (code) DO NOTHING;

-- ==========================================
-- 2. SUPER ADMIN
-- ==========================================
INSERT INTO users (
    first_name, last_name, email, password_hash, role,
    is_active, video_call_notifications, video_call_email_reminders,
    preferred_video_quality, account_locked, is_online, created_at
) VALUES (
    'System', 'Administrator', 'superadmin@lspu.edu.ph',
    'scrypt:32768:8:1$WEEMOGZKSWIayLxJ$227f6b4b74d6052eb2121a07fefcd62cf1c433257bf6686c5dea038fd2aae94a887c0163619309f33e9cf022b4a7ece5118399efb0b0960543b1080dd5b09b2e',
    'super_super_admin',
    TRUE, TRUE, TRUE, 'auto', FALSE, FALSE, CURRENT_TIMESTAMP
) ON CONFLICT (email) DO NOTHING;

-- ==========================================
-- 3. SYSTEM SETTINGS
-- ==========================================
INSERT INTO system_settings (setting_key, setting_value, setting_type, description) VALUES
('APP_NAME', 'PiyuGuide', 'string', 'Name of the Application'),
('MAX_FILE_SIZE', '5242880', 'integer', 'Maximum file upload size in bytes (5MB)'),
('ALLOWED_EXTENSIONS', 'pdf,png,jpg,jpeg', 'string', 'Allowed file extensions for uploads')
ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value;

-- ==========================================
-- 4. CONCERN TYPES
-- ==========================================
DO $$
DECLARE
    v_campus_id INTEGER;
BEGIN
    SELECT id INTO v_campus_id FROM campuses WHERE code = 'LSPU-SHC' LIMIT 1;

    INSERT INTO concern_types (name, description, allows_other, campus_id) VALUES
    -- Registrar
    ('Enrollment-Related Issues', 'Inquiries regarding access problems, verification of subjects, and procedures.', FALSE, v_campus_id),
    ('Issuance of Academic Records & Grade Completion Requests', 'Requests for TOR, certifications, and completion of INC/4.0.', FALSE, v_campus_id),
    ('Account & Portal Issues', 'Concerns related to forgotten email/password or inability to log in.', FALSE, v_campus_id),
    ('Student Record Errors', 'Typographical errors in student information and mismatches with official documents.', FALSE, v_campus_id),
    ('Grades & Academic Status', 'Missing grades, erroneous entries, and requests for grade correction.', FALSE, v_campus_id),
    ('Process-Oriented Inquiries', 'Clarifications related to shifting, dropping, and submitting forms.', FALSE, v_campus_id),
    -- OSAS
    ('Signing of Semestral Clearances', 'Verification and signing of semestral clearance forms.', FALSE, v_campus_id),
    ('Signing of General Clearances (Graduating Students)', 'Final clearance signing for graduating students.', FALSE, v_campus_id),
    ('ID Validation', 'Verification of student identity during enrollment.', FALSE, v_campus_id),
    ('Application, Renewal, and Recognition of Student Organizations', 'Inquiries about ISO process and organization recognition requirements.', FALSE, v_campus_id),
    ('Student Handbook Violations', 'Infractions such as bullying, academic dishonesty, misbehavior, etc.', FALSE, v_campus_id),
    ('Complaint Submission', 'Filing of written complaints against individuals or groups.', FALSE, v_campus_id),
    -- Scholarship
    ('Scholarship Slots and Application', 'Inquiries regarding the availability of scholarship slots and application period.', FALSE, v_campus_id),
    ('Application Process and Requirements', 'Clarifications on required documents for scholarship applications.', FALSE, v_campus_id),
    ('Stipend Release and Follow-Up', 'Questions about expected release dates of scholarship stipends.', FALSE, v_campus_id),
    ('Follow-up on Scholarship Applications', 'Tracking the status of submitted scholarship applications.', FALSE, v_campus_id),
    -- Guidance
    ('Behavioral or Disciplinary Counseling', 'Counseling sessions provided to students sanctioned for rule violations.', FALSE, v_campus_id),
    ('Counseling for Emotional Support', 'Immediate assistance for students experiencing emotional distress.', FALSE, v_campus_id),
    ('Peer conflict Resolution', 'Mediation or guidance for students experiencing conflicts with fellow students.', FALSE, v_campus_id),
    ('Bullying Related Issues', 'Inquiries involving reported cases of bullying.', FALSE, v_campus_id),
    ('Parental Involvement and Family-Triggered Counseling', 'Counseling facilitated with involvement of parents or guardians.', FALSE, v_campus_id),
    -- BAO
    ('Selling of Uniforms', 'Inquiries regarding specifications, sizes, availability, and payment options for uniforms.', FALSE, v_campus_id),
    ('ID Processing', 'Processing of student identification cards including requirements and timelines.', FALSE, v_campus_id),
    -- GAD
    ('Availability and Usage of GAD Services', 'Questions regarding how to access the office support services.', FALSE, v_campus_id),
    ('Gender-Based Violence or Discrimination', 'Reporting or clarifying issues related to harassment or discrimination based on gender.', FALSE, v_campus_id),
    ('Pregnancy-Related Concerns', 'Academic support, health referrals, or accommodations due to pregnancy.', FALSE, v_campus_id),
    ('Assistance for Students with Special Needs', 'Requests for accommodations or help regarding disabilities.', FALSE, v_campus_id),
    ('Request for Consultation Schedule', 'Booking a consultation session with the GAD counselor or officer.', FALSE, v_campus_id),
    ('Request for GAD Speakers or Resource Persons', 'Requests for GAD personnel to participate in events/seminars.', FALSE, v_campus_id),
    ('Academic Research Topics Related to GAD', 'Inquiries from students conducting research involving gender/development themes.', FALSE, v_campus_id),
    ('GAD Collaboration and Partnerships', 'Coordination for instructional activities, research, and community development.', FALSE, v_campus_id),
    -- ICTS
    ('Web Posting', 'Process and requirements for posting content on the university official website.', FALSE, v_campus_id),
    ('Computer Repair and Servicing', 'Maintenance and repair of university computers.', FALSE, v_campus_id),
    ('Preventive Maintenance', 'Scheduled preventive maintenance activities for university IT equipment.', FALSE, v_campus_id),
    -- Cashier
    ('Collection of Fees', 'Payment of tuition, laboratory, and other charges.', FALSE, v_campus_id),
    ('Releasing of Checks', 'Process of releasing checks for students/faculty.', FALSE, v_campus_id),
    ('Releasing of Cash', 'Disbursement of cash for allowances or reimbursements.', FALSE, v_campus_id),
    -- Clinic
    ('Requirements for Medical Appointments', 'Documents needed to schedule a medical appointment.', FALSE, v_campus_id),
    ('Medical Scheduling', 'Schedule for medical checkups and physician availability.', FALSE, v_campus_id),
    ('Medical Certificate Requests', 'Securing medical certificates for absences or requirements.', FALSE, v_campus_id),
    ('Health-Related Consultations', 'Seeking medical advice or in-person consultation.', FALSE, v_campus_id),
    ('Endorsements for Medical Procedures', 'Referrals for external medical needs or hospital procedures.', FALSE, v_campus_id),
    ('Routine Medical and Dental Services', 'Basic medical and dental checkups.', FALSE, v_campus_id),
    ('Annual Physical Examination of Faculty and Personnel', 'Mandatory yearly checkups of LSPU employees.', FALSE, v_campus_id),
    ('Medical Screening for Newly Hired Faculty and Personnel', 'Process and required forms for new employees.', FALSE, v_campus_id),
    -- Library
    ('Library Reference Assistance', 'Identifying, locating, and citing library resources.', FALSE, v_campus_id),
    ('Library Circulation Service', 'Borrowing procedures, book return deadlines, and overdue fines.', FALSE, v_campus_id),
    ('Use of Library Facilities and Equipment', 'Reserving or accessing study areas, computers, and printers.', FALSE, v_campus_id),
    ('Electronic Resources', 'Assistance in accessing online books, journals, and academic databases.', FALSE, v_campus_id),
    ('Access to Resources', 'Access requirements for LSPU and non-LSPU students.', FALSE, v_campus_id),
    ('Hiring of Student Assistants (SA)', 'Qualifications, application process, and deadlines for SA postings.', FALSE, v_campus_id),
    ('Faculty Recommendations', 'Accessing faculty-assigned reference materials.', FALSE, v_campus_id)
    ON CONFLICT (campus_id, name) DO NOTHING;
END $$;

-- ==========================================
-- 5. OFFICES & RELATIONSHIPS
-- ==========================================
DO $$
DECLARE
    v_campus_id INTEGER;
    v_office_id INTEGER;
    c_id INTEGER;
BEGIN
    SELECT id INTO v_campus_id FROM campuses WHERE code = 'LSPU-SHC' LIMIT 1;

    -- 1. Registrar
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('Office of the Registrar', 'Handles academic records, enrollment matters, subject additions/dropping, includes transcript requests, COR issues, document certification, admission requirements, transfer applications, and graduation evaluations.', FALSE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Enrollment-Related Issues', 'Issuance of Academic Records & Grade Completion Requests',
        'Account & Portal Issues', 'Student Record Errors', 'Grades & Academic Status', 'Process-Oriented Inquiries'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, FALSE);
    END LOOP;

    -- 2. OSAS
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('Office of Student Affairs and Services (OSAS)', 'Manages student activities, student ID concerns, student handbook, student organization activity requests, lost and found, and certificates of good moral character. It also handles student welfare and disciplinary matters.', FALSE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Signing of Semestral Clearances', 'Signing of General Clearances (Graduating Students)',
        'ID Validation', 'Application, Renewal, and Recognition of Student Organizations',
        'Student Handbook Violations', 'Complaint Submission'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, FALSE);
    END LOOP;

    -- 3. Scholarship
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('Scholarship and Financial Assistance Office', 'Handles scholarship certifications, scholarship application status, waivers, and financial assistance programs. It also assists with financial aid inquiries and any budget-related student concerns.', FALSE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Scholarship Slots and Application', 'Application Process and Requirements',
        'Stipend Release and Follow-Up', 'Follow-up on Scholarship Applications'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, FALSE);
    END LOOP;

    -- 4. Guidance
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('Guidance and Counseling Office', 'Offers personal and academic counseling, psychological tests, career guidance, special case referrals, and mental health concerns. It provides confidential support, consultations, and academic advice.', TRUE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Behavioral or Disciplinary Counseling', 'Counseling for Emotional Support',
        'Peer conflict Resolution', 'Bullying Related Issues', 'Parental Involvement and Family-Triggered Counseling'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, FALSE, TRUE);
    END LOOP;

    -- 5. BAO
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('Business Affairs Office (BAO)', 'Manages student payments, billing inquiries, payment verification, issuance of official receipts, and other pricing and costing. Inquiries may include refund requests and any other related student issues.', FALSE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Selling of Uniforms', 'ID Processing'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, FALSE);
    END LOOP;

    -- 6. GAD
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('Gender and Development Office (GAD)', 'Handles gender-related events, gender sensitivity training, counseling referrals, and advocacy initiatives. It focuses on gender equality and inclusivity programs.', TRUE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Availability and Usage of GAD Services', 'Gender-Based Violence or Discrimination',
        'Pregnancy-Related Concerns', 'Assistance for Students with Special Needs',
        'Request for Consultation Schedule', 'Request for GAD Speakers or Resource Persons',
        'Academic Research Topics Related to GAD', 'GAD Collaboration and Partnerships'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, TRUE);
    END LOOP;

    -- 7. ICTS
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('ICT Services (ICTS) Office', 'Manages ID registration, barcode activation, student portal account issues, and LSPU email requests. It also handles system updates and ID or portal login problems.', FALSE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Web Posting', 'Computer Repair and Servicing', 'Preventive Maintenance'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, FALSE);
    END LOOP;

    -- 8. Cashier
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('Office of the Cashier', 'Handles the assessment and collection of tuition and other school fees. It is also responsible for the issuance of official receipts, processing of payment transactions and recording of student fees.', FALSE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Collection of Fees', 'Releasing of Checks', 'Releasing of Cash'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, FALSE);
    END LOOP;

    -- 9. Clinic
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('University Clinic', 'Provides medical consultations, check-ups, drug testing, laboratory exams, and medical clearances. It is also the office for heat result issuance, physical exams, and medical certificates.', FALSE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Requirements for Medical Appointments', 'Medical Scheduling', 'Medical Certificate Requests',
        'Health-Related Consultations', 'Endorsements for Medical Procedures', 'Routine Medical and Dental Services',
        'Annual Physical Examination of Faculty and Personnel', 'Medical Screening for Newly Hired Faculty and Personnel'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, FALSE);
    END LOOP;

    -- 10. Library
    INSERT INTO offices (name, description, supports_video, campus_id)
    VALUES ('University Library', 'Provides access to a wide range of academic resources including books, journals, and digital materials. It helps the office for library card issuance, borrowing and returning of materials, and research assistance.', FALSE, v_campus_id)
    RETURNING id INTO v_office_id;

    FOR c_id IN SELECT id FROM concern_types WHERE name IN (
        'Library Reference Assistance', 'Library Circulation Service', 'Use of Library Facilities and Equipment',
        'Electronic Resources', 'Access to Resources', 'Hiring of Student Assistants (SA)', 'Faculty Recommendations'
    ) LOOP
        INSERT INTO office_concern_types (office_id, concern_type_id, for_inquiries, for_counseling) VALUES (v_office_id, c_id, TRUE, FALSE);
    END LOOP;

END $$;

COMMIT;
