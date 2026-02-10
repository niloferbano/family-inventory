

# 📦 Family Inventory & Notification System

## 🧩 Problem Statement

The motivation behind this project stems from the difficulty in keeping track of and tidying products at home, which often leads to missed expiries and unnecessary waste. This system aims to solve these challenges by providing timely notifications and a streamlined inventory management experience.


A **production-grade, event-driven notification system** built around an inventory management domain.  
The system detects expiring inventory items and delivers notifications via **user-configurable channels**, including a **real-time in-app inbox**.

> This project demonstrates event-driven architecture, broker-managed retries, idempotency, distributed workers, and real-time delivery.

---

## 🚀 Features

### Inventory
- Homes with multiple users
- Inventory items with expiry dates
- Background job emits expiry events

### Notifications
- Topic-based subscriptions (e.g. `inventory.item.expired`)
- Per-user channel preferences
- Supported channels:
  - 🛎 **In-App Inbox (real-time)**
  - 📄 Log (pluggable)
  - 📧 Email (extensible)

### Reliability
- Outbox pattern for event publishing
- Broker-managed retries (RabbitMQ TTL + DLX)
- Dead-letter queue (DLQ)
- Idempotent event ingestion
- Distributed delivery claiming (safe for multiple workers)

### Real-Time
- WebSocket push for in-app notifications
- Redis Pub/Sub for multi-replica fan-out
- Read/unread state + badge count

---

## 🧱 Architecture Overview

```
Inventory Service
   │
   │ emits event
   ▼
Notification Outbox
   │
   │ publishes
   ▼
RabbitMQ (topic exchange + retry queues)
   │
   │ consume
   ▼
Notification Worker
   │
   │ deliver
   ▼
notification_inbox (Postgres)
   │
   │ push
   ▼
WebSocket / Redis → UI
```

---

inventory job → outbox row → (dispatcher) publish to RabbitMQ → notification worker consumes → ingest creates delivery rows → sender writes in_app_notifications


InventoryExpiryJob
  └─ writes NotificationOutbox (transactional)
  └─ best-effort publish

Outbox Sweeper
  └─ UPDATE ... RETURNING (claim)
  └─ publish
  └─ mark SENT / FAILED

Notification Worker
  └─ consumes broker events
  └─ creates NotificationDelivery rows
  └─ InAppSender writes inbox

## 🧠 Key Design Decisions

### Event-Driven + Outbox Pattern
- Inventory never talks to Notification directly
- Events are persisted first, then published
- Guarantees **no lost events**

### Broker-Managed Retries
- Failed messages are routed to TTL retry queues
- Automatic redelivery after delay
- Messages go to DLQ after max retries

### Idempotency
- `event_id` is the primary identifier everywhere
- Inbox uses `(user_id, event_id)` uniqueness
- Safe replays and retries

### Distributed Workers
- Delivery rows are **claimed with DB leases**
- `SELECT … FOR UPDATE SKIP LOCKED`
- Multiple workers can run safely

### Real-Time Fan-out
- Redis Pub/Sub decouples WebSocket layer
- WebSocket servers stay stateless

---

## 🛠 Tech Stack

- Python 3.12
- FastAPI
- PostgreSQL
- SQLAlchemy (async)
- RabbitMQ
- Redis
- WebSockets
- Docker & Docker Compose

---

## 🧪 Running Locally

```bash
make up
make db-upgrade
make run
make worker
```

---

## 🔔 Demo Flow

1. Create a home + user
2. Add an inventory item with an expired date
3. Inventory job emits `inventory.item.expired`
4. Notification worker processes event
5. In-app notification appears instantly
6. Badge count increments
7. Mark as read → badge updates

---

## 🔐 Security
- JWT-based authentication
- Home membership enforcement
- Inbox scoped per user

---

## ⚠️ Failure Scenarios & Guarantees

- RabbitMQ down at publish time (outbox + retry on reconnect)
- Worker crash mid-delivery (DB lease expires, another worker retries)
- Duplicate events (idempotent event_id handling)
- Notification channel failure (broker-managed retries, DLQ after max attempts)

---
## 💼 Resume Highlights

- Event-driven architecture with RabbitMQ
- Broker-managed retries & DLQ
- Distributed workers with DB-level locking
- Real-time WebSocket delivery with Redis
- Async Python with FastAPI & SQLAlchemy

---


## 🚧 Future Improvements
- Email/SMS providers
- Notification prioritization
- Tracing & metrics
- UI grouping & pagination
- add notification_templates table + admin endpoints + caching

---
