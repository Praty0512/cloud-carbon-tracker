"""Background sync runner for queued connector jobs."""

from __future__ import annotations

from engine.connector_worker import execute_due_jobs


def main() -> None:
    """Run a single scheduler pass for due connector jobs."""
    results = execute_due_jobs(limit=10)
    if not results:
        print("No due connector jobs were found.")
        return

    print(f"Processed {len(results)} connector job(s).")
    for result in results:
        print(f"[{result.status}] {result.summary}")


if __name__ == "__main__":
    main()
