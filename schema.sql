-- Run this file in MySQL Workbench (or `mysql -u root -p < schema.sql`)
-- to create the database and tables before starting the Flask app.

CREATE DATABASE IF NOT EXISTS student_management;
USE student_management;

CREATE TABLE IF NOT EXISTS admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL   -- stores a hashed password, never plain text
);

CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL UNIQUE,
    student_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    phone VARCHAR(15),
    gender ENUM('Male', 'Female', 'Other'),
    date_of_birth DATE,
    course VARCHAR(50) NOT NULL,
    semester INT NOT NULL,
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- A few sample rows so the dashboard and student list have something to show
-- immediately. Feel free to delete these once you've added real data.
INSERT INTO students
    (student_id, student_name, email, phone, gender, date_of_birth, course, semester, address)
VALUES
    ('BCA2401', 'Aarav Sharma', 'aarav.sharma@example.com', '9876543210', 'Male', '2005-04-12', 'BCA', 3, 'Aurangabad, Maharashtra'),
    ('BCA2402', 'Priya Deshmukh', 'priya.deshmukh@example.com', '9876543211', 'Female', '2005-08-23', 'BCA', 3, 'Pune, Maharashtra'),
    ('BCA2403', 'Rohan Patil', 'rohan.patil@example.com', '9876543212', 'Male', '2004-11-02', 'BCA', 5, 'Nashik, Maharashtra'),
    ('BCA2404', 'Sneha Kulkarni', 'sneha.kulkarni@example.com', '9876543213', 'Female', '2005-01-17', 'BCA', 1, 'Aurangabad, Maharashtra');
