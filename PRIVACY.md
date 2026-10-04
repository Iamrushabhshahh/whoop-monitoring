# Privacy policy — whoop-monitoring

whoop-monitoring is a personal, unofficial, self-hosted tool. It is not a service and is not affiliated with WHOOP, Inc.

- **What it reads:** your WHOOP cycles, recovery, sleep, workouts, body measurements and basic
  profile, with the scopes you approve.
- **Where data goes:** only to the OpenObserve instance that you run. No third party gets it.
- **What it does not store:** your name and email. The profile is read only to show your user id.
- **Tokens:** stored on your machine in `data/tokens.json`, readable only by your user.
- **Delete:** run `whoopmon auth logout` to revoke access at WHOOP and delete local tokens.
  Delete the `whoop_*` streams in OpenObserve to remove the data.

Contact: open an issue on the repository.
