// root dev wiring stub
terraform { required_version = ">= 1.6.0" }
provider "aws" { region = var.region }

module "network" { source = "../../modules/network" }
module "opensearch_serverless" { source = "../../modules/opensearch_serverless" }
module "storage" { source = "../../modules/storage" }
module "security" { source = "../../modules/security" }
module "queues" { source = "../../modules/queues" }
module "edge" { source = "../../modules/edge" }
module "cognito" { source = "../../modules/cognito" }
module "ecs_api" { source = "../../modules/ecs_service" }
module "ecs_agents" { source = "../../modules/ecs_service" }
module "ecs_scraper" { source = "../../modules/ecs_service" }
