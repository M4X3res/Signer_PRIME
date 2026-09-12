# Changelog

All notable changes to Signer License Server will be documented in this file.

## [1.0.0] - 2026-09-12

### Added
- **Core functionality**
  - FastAPI application with PostgreSQL backend
  - Ed25519 token signing and verification
  - License activation, refresh, and deactivation endpoints
  - Rate limiting on critical endpoints (10/min activate, 20/min refresh)
  
- **Database**
  - Alembic migrations with partial unique index
  - SELECT FOR UPDATE protection against race conditions
  - Cloud SQL and local Postgres support
  
- **Security**
  - Admin API with X-Admin-Key authentication
  - Stripe webhook signature verification
  - Secret Manager integration for production secrets
  
- **Stripe Integration**
  - Automatic license creation from checkout.session.completed
  - Subscription status updates (customer.subscription.updated)
  - Subscription cancellation handling (customer.subscription.deleted)
  
- **Testing**
  - Full test suite with testcontainers (real Postgres 16)
  - Race condition test for concurrent activation
  - Webhook security test for invalid signatures
  - Rate limiting tests
  
- **Deployment**
  - Multi-stage Docker build for production
  - docker-compose.dev.yml for local development
  - Idempotent GCP deployment script
  - Cloud Run service with automatic migrations
  
- **Utilities**
  - create_license_manual.py - CLI for manual license creation
  - generate_ed25519_keys.py - Key pair generator with instructions
  - smoke_test.py - Pre-deployment sanity checks

### Changed
- Removed MVP in-memory fallback (production-only mode)
- Replaced create_all() with Alembic migrations

### Fixed
- Duplicate code in app/main.py after if __name__ block
- Missing BaseModel import in old MVP routes

### Documentation
- Comprehensive README.md with quickstart and deployment guide
- STATUS.md with acceptance criteria checklist
- Removed conflicting markdown reports (100_PERCENT_DONE.md, etc.)

## [0.1.0] - 2026-09-11

### Added
- Initial MVP implementation with in-memory storage
- Basic license activation and refresh
- Stripe webhook skeleton

---

## Future Enhancements

### Planned
- [ ] Email notifications for license creation (Stripe checkout)
- [ ] Admin dashboard UI
- [ ] License usage analytics
- [ ] Webhook retry queue with dead letter handling
- [ ] Multi-region deployment support

### Under Consideration
- [ ] GraphQL API alongside REST
- [ ] License transfer between devices
- [ ] Temporary license suspension
- [ ] Usage-based billing integration
