#!/usr/bin/env python

# Written by Joseph "jetole" Tole on 10/31/11
# This is a simple script because I saw the idea of monitoring failed jobs at
# http://goo.gl/qDqGL (shortened Nagios Exchange URL) however I really didn't
# want to implement an unnecessarily complex, multi part, compiled java program
# on my nagios hosts to perform this same check. I added a couple features as
# well such as listing the failed jobs and the time they had last run as well
# as allowing you to specify a single job to check which will return
# OK|CRITICAL for that job alone.

import argparse
import pymssql

# 0 - OK
# 1 - Warning
# 2 - Critical
# 3 - Unknown
def nagios_exit(exit_type, msg):
    try:
        exit_code=int(exit_type)
        if exit_code < 0 or exit_code > 2:
            exit_code = 3
    except ValueError:
        exit_code=3

    if exit_code == 0:
        status = "OK"
    elif exit_code == 1:
        status = "WARNING"
    elif exit_code == 2:
        status = "CRITICAL"
    else:
        status = "UNKNOWN"

    print "%s - %s" % (status, msg)
    exit(exit_code)

    
def run_datetime(run_date, run_time):
    run_date = str(run_date)
    run_time = str("%06d" % (int(run_time)))

    run_year = run_date[0:4]
    run_month = run_date[4:6]
    run_day = run_date[6:8]
    run_hour = run_time[0:2]
    run_minute = run_time[2:4]
    run_second = run_time[4:6]

    return "%s/%s/%s %s:%s:%s" % (run_month, run_day, run_year, run_hour, run_minute, run_second)


parser = argparse.ArgumentParser(description="Check a SQL Server for failed jobs - results based on state of last run for all jobs or for a specific job if specified")
parser.add_argument("-t", "--timeout", action="store", type=int, help="Timeout for connection and login in seconds", default="60", dest="timeout")
parser.add_argument("--query-timeout", action="store", type=int, help="Query timeout in seconds", default="60", dest="query_timeout")
parser.add_argument("-w", "--warning", action="store", type=int, help="Failed jobs before a warning alert is generated", default="0", dest="warning")
parser.add_argument("-c", "--critical", action="store", type=int, help="Failed jobs before a critical alert is generated", default="1", dest="critical")
parser.add_argument("-H", "--host", action="store", help="Host name or IP address to connect to", required=True, dest="host")
parser.add_argument("-p", "--port", action="store", type=int, help="SQL Server port number (only change if you know you need to)", default=1433, dest="port")
parser.add_argument("-U", "--user", action="store", help="User name to connect as (does not support Windows built in or Active Directory accounts)", required=True, dest="user")
parser.add_argument("-P", "--password", action="store", help="Password to for user you are authenticating as", required=True, dest="password")
parser.add_argument("-j", "--job", action="store", help="A comma seperate list of jobs to check instead of all enabled jobs", dest="job");
parser.add_argument("-x", "--exclude", action="store", help="A comma seperated list of jobs not to check", dest="exclude");
parser.add_argument("-l", "--list", action="store_true", help="This will list all jobs in on your server. This does not return a nagios check and is used for setup and debugging", dest="list_jobs")
parser.add_argument("-v", "--verbose", action="store_true", help="This shows the Transaction SQL code that will be executed to help debug", dest="verbose")
results = parser.parse_args()

try:
    conn = pymssql.connect(user = results.user, password = results.password, host = results.host, timeout = results.query_timeout, login_timeout = results.timeout)
except:
    nagios_exit(3, "Unable to connect to SQL Server")

cur = conn.cursor()

if results.list_jobs:
    tsql_cmd = """ SELECT [name], [enabled]
    FROM [msdb]..[sysjobs]"""

    if results.verbose:
        print "%s\n" % (tsql_cmd)

    cur.execute(tsql_cmd)
    rows = cur.fetchall()

    print "Jobs on %s" % (results.host)
    print "\"-\" at the begining means the job is disabled\n"

    for row in rows:
        if int(row[1]) == 1:
            print "  %s" % (row[0])
        else:
            print "- %s" % (row[0])
    exit()

tsql_cmd = """SELECT [j].[name], [h].[run_date], [h].[run_time]
FROM [msdb]..[sysjobs] [j]
INNER JOIN [msdb]..[sysjobhistory] [h] ON [j].[job_id] = [h].[job_id]
INNER JOIN (
    SELECT [job_id], MAX(instance_id) AS max_instance_id
    FROM [msdb]..[sysjobhistory]
    GROUP BY [job_id]
) [tmp_sjh] ON [h].[job_id] = [tmp_sjh].[job_id] AND [h].[instance_id] = [tmp_sjh].[max_instance_id]
WHERE [j].[enabled] = 1
AND [h].[run_status] = 0"""

if results.job:
    tsql_cmd += "\nAND (\n\t[j].[name] = '%s'" % (results.job.split(',')[0].strip())

    if len(results.job.split(',')) > 1:
        for x in results.job.split(',')[1:]:
            tsql_cmd += "\n\tOR [j].[name] = '%s'" % (x.strip())

    tsql_cmd += "\n)"

elif results.exclude:
    for x in results.exclude.split(','):
        tsql_cmd += "\nAND [j].[name] != '%s'" % (x.strip())

if results.verbose:
    print "%s\n" % (tsql_cmd)

cur.execute(tsql_cmd)
rows = cur.fetchall()
rowcount = cur.rowcount

if rowcount == 0:
    nagios_exit(0, "All jobs completed successfully on their last run")
else:
    failed_stats = "Number of failed jobs: %d - Failed Jobs: " % (rowcount)
    for row in rows:
        failed_stats += "%s last run at %s, " % (row[0], run_datetime(row[1], row[2]))
    failed_stats = failed_stats.rstrip(', ')

    if rowcount >= results.warning and rowcount < results.critical:
        nagios_exit(1, failed_stats)
    elif rowcount < results.warning:
        nagios_exit(0, "%d failed jobs is below the warning count specified." % (rowcount))
    elif rowcount >= results.critical:
        nagios_exit(2, failed_stats)
    else:
        nagios_exit(3, "This should never appear")
