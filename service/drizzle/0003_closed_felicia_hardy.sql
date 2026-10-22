ALTER TABLE `subscriptions` ADD `pending_secret` text;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `pending_expires` integer;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `verify_until` integer;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `verify_generation` integer DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `verified_at` integer;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `last_refresh_requested` integer;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `last_refresh_completed` integer;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `refresh_requests` integer DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `refresh_successes` integer DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE `subscriptions` ADD `refresh_error` text;