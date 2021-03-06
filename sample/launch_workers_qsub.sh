#!/bin/bash
#
# Example shell script for running job that runs off the Wilmerlab subjobserver.
# $Revision: 1.0 $
# $Date:  2016-03-21 $
# $Author: paulboone $

#PBS -j oe
#PBS -N your project_name
#PBS -q test
#PBS -l nodes=1:ppn=1
#PBS -l walltime=00:30:00
#PBS -l mem=1GB
#PBS -S /bin/bash

# accepts a parameter stay_alive if you don't want the worker to exit immediately after all jobs
# are complete
# use like `qsub -v stay_alive=1`

echo JOB_ID: $PBS_JOBID JOB_NAME: $PBS_JOBNAME HOSTNAME: $PBS_O_HOST
echo start_time: `date`

if [ "$PBS_NUM_NODES" -gt "1" ]; then
  echo "
This script only supports launching workers on one node at a time.
You can launch multiple nodes by running the script multiple times.

(This is due to a limitation of how Frank is setup; when we switch over to
the new servers, this limitation should go away).
"
  exit 64
fi

# dependencies
module purge
module load python/3.5.1

## CHANGE THIS LINE TO LOAD YOUR PROJECT'S VENV:
# source ~/venv/sensor_ads/bin/activate

cd $PBS_O_WORKDIR
sjs_launch_workers.sh $PBS_NUM_PPN $stay_alive

# workaround for .out / .err files not always being copied back to $PBS_O_WORKDIR
cp /var/spool/torque/spool/$PBS_JOBID.OU $PBS_O_WORKDIR/$PBS_JOBID$(hostname)_$$.out
cp /var/spool/torque/spool/$PBS_JOBID.ER $PBS_O_WORKDIR/$PBS_JOBID$(hostname)_$$.err

exit
