import logging
import sys
import time

import click

from autoscaler.cluster import Cluster
from autoscaler.notification import Notifier

logger = logging.getLogger('autoscaler')

DEBUG_LOGGING_MAP = {
    0: logging.CRITICAL,
    1: logging.WARNING,
    2: logging.INFO,
    3: logging.DEBUG
}


@click.command()
@click.option("--container-service-name", default=None, help='container service name (only for ACS, not acs-engine)')
@click.option("--resource-group")
@click.option("--sleep", default=60)
@click.option("--kubeconfig", default=None,
              help='Full path to kubeconfig file. If not provided, '
                   'we assume that we\'re running on kubernetes.')
@click.option("--parameters-file", default=None,
              help='Full path to the ARM template parameters file. Needed only if running on acs-engine (and not ACS).')
@click.option("--parameters-file-url", default=None,
              help='URL to the ARM template parameters file. Needed only if running on acs-engine (and not ACS).')
@click.option("--template-file", default=None,
              help='Full path to the ARM template file. Needed only if running on acs-engine (and not ACS).')
@click.option("--template-file-url", default=None,
              help='URL to the ARM template file. Needed only if running on acs-engine (and not ACS).')
@click.option("--bypass-sla", is_flag=True, help='WARNING, by enabling this flag you will void the SLA of your ACS cluster. This flags improves the scaling down process. No effect on acs-engine clusters.')
@click.option("--over-provision", default=5)
#how soon after a node becomes idle should we terminate it?
@click.option("--idle-threshold", default=600)

#How many agents should we keep even if the cluster is not utilized? The autoscaler will currenty break if --spare-agents == 0
@click.option("--spare-agents", default=1) 
@click.option("--service-principal-app-id", default=None, envvar='AZURE_SP_APP_ID')
@click.option("--service-principal-secret", default=None, envvar='AZURE_SP_SECRET')
@click.option("--service-principal-tenant-id", default=None, envvar='AZURE_SP_TENANT_ID')
@click.option("--datadog-api-key", default=None, envvar='DATADOG_API_KEY')
@click.option("--instance-init-time", default=25 * 60)
@click.option("--no-scale", is_flag=True)
@click.option("--no-maintenance", is_flag=True)
@click.option("--slack-hook", default=None, envvar='SLACK_HOOK',
              help='Slack webhook URL. If provided, post scaling messages '
                   'to Slack.')
@click.option("--slack-bot-token", default=None, envvar='SLACK_BOT_TOKEN',
              help='Slack bot token. If provided, post scaling messages '
                   'to Slack users directly.')
@click.option("--dry-run", is_flag=True)
@click.option('--verbose', '-v',
              help="Sets the debug noise level, specify multiple times "
                   "for more verbosity.",
              type=click.IntRange(0, 3, clamp=True),
              count=True)
#Debug mode will explicitly surface erros
@click.option("--debug", is_flag=True) 
def main(container_service_name, resource_group, sleep, kubeconfig,
         service_principal_app_id, service_principal_secret, service_principal_tenant_id,
         datadog_api_key,idle_threshold, spare_agents, bypass_sla,
         template_file, parameters_file, template_file_url, parameters_file_url,
         over_provision, instance_init_time, no_scale, no_maintenance,
         slack_hook, slack_bot_token, dry_run, verbose, debug):
    logger_handler = logging.StreamHandler(sys.stderr)
    logger_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(logger_handler)
    logger.setLevel(DEBUG_LOGGING_MAP.get(verbose, logging.CRITICAL))

    if not (service_principal_app_id and service_principal_secret and service_principal_tenant_id):
        logger.error("Missing Azure credentials. Please provide aws-service_principal_app_id, service_principal_secret and service_principal_tenant_id.")
        sys.exit(1)
    
    if (template_file and not parameters_file) or (not template_file and parameters_file):
        logger.error("Both --template-file and --parameters-file should be provided when running on acs-engine")
        sys.exit(1)
    
    if (template_file and template_file_url):
        logger.error('--template-file and --template-file-url are mutually exclusive.')
        sys.exit(1)
    
    if (parameters_file and parameters_file_url):
        logger.error('--parameters-file and --parameters-file-url are mutually exclusive.')
        sys.exit(1)
        
    if template_file and container_service_name:
        logger.error("--template-file and --container-service-name cannot be specified simultaneously. Provide --container-service-name when running on ACS, or --template-file and --parameters-file when running on acs-engine")
        sys.exit(1)
        
    notifier = None
    if slack_hook and slack_bot_token:
        notifier = Notifier(slack_hook, slack_bot_token)
    
    cluster = Cluster(service_principal_app_id=service_principal_app_id,
                      service_principal_secret=service_principal_secret,
                      service_principal_tenant_id=service_principal_tenant_id,
                      kubeconfig=kubeconfig,
                      template_file=template_file,
                      template_file_url=template_file_url,
                      parameters_file_url=parameters_file_url,
                      parameters_file=parameters_file,
                      idle_threshold=idle_threshold,
                      instance_init_time=instance_init_time,
                      spare_agents=spare_agents,
                      bypass_sla=bypass_sla,
                      container_service_name=container_service_name,
                      resource_group=resource_group,
                      scale_up=not no_scale,
                      maintainance=not no_maintenance,
                      over_provision=over_provision,
                      datadog_api_key=datadog_api_key,
                      notifier=notifier,
                      dry_run=dry_run,
                      )    
    backoff = sleep
    while True:
        scaled = cluster.scale_loop(debug)
        if scaled:
            time.sleep(sleep)
            backoff = sleep
        else:
            logger.warn("backoff: %s" % backoff)
            backoff *= 2
            time.sleep(backoff)


if __name__ == "__main__":
    main()
