from prefect import flow, task
from process.make_silver import MakeSilver


@flow(name="silver-pipeline")
def make_silver_pipeline():
    run_make_silver()

@task
def run_make_silver():
    make_silver = MakeSilver()
    make_silver.run()

if __name__ == "__main__":
    make_silver_pipeline()
