from datetime import datetime
import os
import signal
import subprocess
import sys
from time import sleep

import click
from rq import Worker

import sjs
from sjs.run import get_sjs_running_file, SJS_RUNNING_FILE
from sjs.env_record import save_env_record, read_env_record

def disable_signals():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

def signal_handler(signal_received, frame):
    print("Received signal %s." % signal_received)
    if signal_received == signal.SIGUSR1:
        print("restarting workers...")
        print("not yet implemented")
    else:
        print("exiting...")
        disable_signals()
        sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

@click.command()
@click.argument('num_workers', default=1)
@click.option('--burst/--stay-alive', '-b/ ', default=True)
@click.option('--run-pre-checks/--skip-pre-checks', default=True)
@click.option('--run-env-checks/--skip-env-checks', default=True)
@click.option('--interval', '-n', default=60, help='update interval in seconds')
def launch_workers(num_workers, burst, run_pre_checks, run_env_checks, interval):
    os.makedirs("logs", exist_ok=True)

    if run_pre_checks:
        print("Running pre-checks...")
        sjs.run_pre_worker_checks(exit_on_fail=True)
        print("OK!")
    else:
        print("Skipping pre-checks!")

    working_dir = get_sjs_running_file()
    if not working_dir:
        raise SystemExit("Currently there is no run started (i.e. there is no %s file). " \
            "Are you in the correct directory?" % SJS_RUNNING_FILE)

    hostname = os.uname()[1]
    timestamp = datetime.now().strftime("%Y_%m_%d__%H_%M_%S")

    # compare env_record at start of run with this one
    env_record_dir = os.path.join(working_dir, 'env_records')
    env_record_path = os.path.join(env_record_dir, "%s_%s" %(hostname, timestamp))
    env = save_env_record(env_record_path)
    orig_env_record = read_env_record(os.path.join(env_record_dir, 'env_record_start.yaml'))
    if run_env_checks:
        print("Running env-checks...")
        if env != orig_env_record:
            print("env_record of this machine does not match env record of original machine! " \
                "Aborting launch workers! Please see %s to compare manually" % (env_record_path))
            raise SystemExit("Env records do not match, aborting launch workers!")
        else:
            print("OK!")
    else:
        print("Skipping env-checks!")

    print("")
    print("Running on hostname %s" % hostname)
    print("Running at timestamp %s" % timestamp)
    print("Log name template: %s_%s_*.log" % (hostname, timestamp))
    print("Env record path: %s" % env_record_path)
    if burst:
        print("Running in burst mode. Workers and launch_workers script will exit when all " \
              "workers are idle and the queue is empty.")
    else:
        print("Workers and launch_workers script will stay alive until killed.")

    print("")
    worker_processes = []
    log_files = []

    sjs.load()
    sjs_config = sjs.get_sjs_config()
    redis_cfg = sjs_config['redis']
    redis_url = "redis://%s:%s/%s" % (redis_cfg['host'], redis_cfg['port'], redis_cfg['db'])
    cmd = ['rq', 'worker', "-u", redis_url, sjs_config['queue']]

    for i in range(num_workers):
        logname = 'logs/%s_%s_%s.log' % (hostname, timestamp, i)
        print("Launching worker #%s with log file %s" % (i, logname))

        log = open(logname, 'w')
        proc = subprocess.Popen(cmd, stdout=log, stderr=log)

        worker_processes.append(proc)
        log_files.append(log)

    print("")
    print("Worker PIDS: %s" % [w.pid for w in worker_processes])

    try:
        conn = sjs.get_redis_conn()

        if 'min_seconds_per_job' in sjs_config or burst == False:
            # more complex case of either handling bursted workers, or handling min_seconds_per_job
            # timeout. Here we run a loop and check conditions each run through the loop.
            while True:
                sleep(interval)

                if burst:
                    # there is no point killing workers on the node unless all of them are idle and
                    # we can kill all the workers and release the node. So here we poll for the
                    # current worker state and if all the workers are idle AND the queue is empty,
                    # then we shut the node down.
                    workers = [ w for w in Worker.all(connection=conn) if w.name.startswith(hostname)]
                    idle_workers = [ w for w in workers if w.state == 'idle' ]
                    if len(idle_workers) == len(workers) and len(sjs.get_job_queue()) == 0:
                        print("All workers idle; queue is empty.")
                        disable_signals()
                        raise SystemExit()

                if 'min_seconds_per_job' in sjs_config:
                    try:
                        results = subprocess.check_output("qstat -i $PBS_JOBID", shell=True, universal_newlines=True)
                        hours, minutes, seconds = results.strip().split("\n")[-1][-8:].split(":")
                        walltime_remaining = int(hours) * 3600 + int(minutes) * 60 + int(seconds)

                        if sjs_config['min_seconds_per_job'] > walltime_remaining:
                            print("walltime remaining is less than the min seconds required per " \
                                  "job. Sending SIGINTs to workers so they exit when the " \
                                  "currently running job is complete")
                            for worker in worker_processes:
                                os.kill(worker.pid, signal.SIGINT)
                            break

                    except Exception as e:
                        print("Failure getting walltime", e)

        # the simplest case of just running the workers until they exit
        print("Waiting for workers to exit...")
        for w in worker_processes:
            w.wait()

    except SystemExit:
        # if this process is forced to exit, we kill the workers, and wait for them to
        # exit, before finally closing the log files.
        print("... killing any workers")

        # rq workers must be signaled twice to actually shutdown.
        # we sleep in between to avoid a signal getting lost.
        try:
            print("sending first SIGINT")
            os.killpg(os.getpgid(0), signal.SIGINT)
            sleep(1)
            print("sending second SIGINT")
            os.killpg(os.getpgid(0), signal.SIGINT)
        except ProcessLookupError:
            print("process already killed")
        for w in worker_processes:
            w.wait()
    finally:
        for f in log_files:
            f.close()

    print("")
    print("All done!")
    sys.stdout.flush()
