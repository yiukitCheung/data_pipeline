from prefect import flow, task
from process.core.resampler import Resampler


@flow(name="silver-pipeline")
def silver_pipeline():
    resampler()

@task
def resampler():
    make_silver = Resampler()
    make_silver.run()

if __name__ == "__main__":
    silver_pipeline()
