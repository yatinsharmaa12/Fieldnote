from rq import SimpleWorker

from app.queue.crawl_queue import crawl_queue
from app.services.recovery_service import recover_stale_jobs


if __name__ == "__main__":
    recover_stale_jobs()
    worker = SimpleWorker(
        [crawl_queue],
    )

    worker.work()
