-- HoursTracker.admins definition

CREATE TABLE `admins` (
  `id` int NOT NULL AUTO_INCREMENT,
  `email` varchar(50) NOT NULL,
  `name` varchar(50) NOT NULL,
  `status` enum('denied','pending','approved') NOT NULL DEFAULT 'pending',
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- HoursTracker.events definition

CREATE TABLE `events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `date` date DEFAULT NULL,
  `hours` int NOT NULL DEFAULT '0',
  `desc` text,
  `needproof` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE entries(
	id INT AUTO_INCREMENT PRIMARY KEY,
	event_id INTEGER,
	FOREIGN KEY (event_id) REFERENCES events(id),
	name VARCHAR(100),
	sid VARCHAR(20),
	status ENUM('denied','pending','approved')
);
