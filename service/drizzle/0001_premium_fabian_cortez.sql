CREATE TABLE `bridge_events` (
	`seq` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`id` text NOT NULL,
	`owner` text NOT NULL,
	`name` text NOT NULL,
	`job_id` text NOT NULL,
	`payload` text NOT NULL,
	`created` integer NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `bridge_events_id_unique` ON `bridge_events` (`id`);--> statement-breakpoint
CREATE TABLE `bridge_jobs` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`request_id` text NOT NULL,
	`action` text NOT NULL,
	`args` text NOT NULL,
	`status` text NOT NULL,
	`record` text,
	`revision` integer DEFAULT 0 NOT NULL,
	`created` integer NOT NULL,
	`updated` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `bridge_settings` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `deliveries` (
	`id` text PRIMARY KEY NOT NULL,
	`subscription` text NOT NULL,
	`event` text NOT NULL,
	`status` text NOT NULL,
	`attempt` integer DEFAULT 0 NOT NULL,
	`next_attempt` integer DEFAULT 0 NOT NULL,
	`error` text,
	`receipt` integer,
	`ack` integer
);
--> statement-breakpoint
CREATE TABLE `discoveries` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`thread` text NOT NULL,
	`metadata` text NOT NULL,
	`updated` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `subscriptions` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`name` text NOT NULL,
	`args` text NOT NULL,
	`url` text NOT NULL,
	`secret` text NOT NULL,
	`status` text NOT NULL,
	`error` text,
	`expires` integer NOT NULL,
	`created` integer NOT NULL
);
