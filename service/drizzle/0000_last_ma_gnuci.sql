CREATE TABLE `device` (
	`id` text PRIMARY KEY NOT NULL,
	`seen` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `jobs` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`action` text NOT NULL,
	`thread` text NOT NULL,
	`message` text NOT NULL,
	`status` text NOT NULL,
	`result` text,
	`created` integer NOT NULL,
	`updated` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `jobs_status_created` ON `jobs` (`status`,`created`);