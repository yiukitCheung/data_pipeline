from prefect import flow, task
from process.utils import *


@flow(name="silver-pipeline")
def silver_pipeline():
    run_make_silver()

@task
def run_make_silver():
    make_silver = MakeSilver()
    make_silver.run()

@task 
def re 
if __name__ == "__main__":
    silver_pipeline()
