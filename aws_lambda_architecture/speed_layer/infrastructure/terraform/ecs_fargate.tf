# ECS Fargate Configuration for WebSocket Service
# Purpose: Deploy and manage the persistent WebSocket connection service

# ECS Cluster
resource "aws_ecs_cluster" "speed_layer" {
  name = var.ecs_cluster_name != "" ? var.ecs_cluster_name : "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = var.enable_detailed_monitoring ? "enabled" : "disabled"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cluster"
  })
}

# ECS Cluster Capacity Providers (for cost optimization)
resource "aws_ecs_cluster_capacity_providers" "speed_layer" {
  cluster_name = aws_ecs_cluster.speed_layer.name

  capacity_providers = var.enable_spot_instances ? ["FARGATE", "FARGATE_SPOT"] : ["FARGATE"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = var.enable_spot_instances ? 20 : 100
    capacity_provider = "FARGATE"
  }

  dynamic "default_capacity_provider_strategy" {
    for_each = var.enable_spot_instances ? [1] : []
    content {
      base              = 0
      weight            = 80
      capacity_provider = "FARGATE_SPOT"
    }
  }
}

# ECR Repository for WebSocket service
resource "aws_ecr_repository" "websocket_service" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-ecr"
  })
}

# ECR Lifecycle Policy
resource "aws_ecr_lifecycle_policy" "websocket_service" {
  repository = aws_ecr_repository.websocket_service.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Delete untagged images older than 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# CloudWatch Log Group for ECS tasks
resource "aws_cloudwatch_log_group" "websocket_service" {
  name              = "/ecs/${local.name_prefix}-websocket"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-logs"
  })
}

# Security Group for ECS tasks
resource "aws_security_group" "websocket_service" {
  name_prefix = "${local.name_prefix}-websocket-"
  vpc_id      = local.vpc_id
  description = "Security group for WebSocket service ECS tasks"

  # Health check endpoint
  ingress {
    description = "Health check endpoint"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # All outbound traffic (for API calls)
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ECS Task Definition
resource "aws_ecs_task_definition" "websocket_service" {
  family                   = "${local.name_prefix}-websocket"
  requires_compatibilities = ["FARGATE"]
  network_mode            = "awsvpc"
  cpu                     = var.websocket_service_cpu
  memory                  = var.websocket_service_memory
  execution_role_arn      = aws_iam_role.ecs_execution_role.arn
  task_role_arn          = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name  = "websocket-service"
      image = "${aws_ecr_repository.websocket_service.repository_url}:${var.image_tag}"
      
      essential = true
      
      portMappings = [
        {
          containerPort = 8080
          protocol      = "tcp"
          name          = "health-check"
        }
      ]
      
      environment = [
        {
          name  = "POLYGON_API_KEY"
          value = var.polygon_api_key
        },
        {
          name  = "KINESIS_STREAM_NAME"
          value = aws_kinesis_stream.market_data_raw.name
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "LOG_LEVEL"
          value = "INFO"
        },
        {
          name  = "ENVIRONMENT"
          value = var.environment
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.websocket_service.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
      
      healthCheck = {
        command = [
          "CMD-SHELL",
          "curl -f http://localhost:8080/health || exit 1"
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
      
      # Resource limits
      memoryReservation = var.websocket_service_memory * 0.8
      
      # Security
      readonlyRootFilesystem = false
      user                  = "speedlayer"
    }
  ])

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-task"
  })
}

# Application Load Balancer (for health checks and potential future scaling)
resource "aws_lb" "websocket_service" {
  name               = "${local.name_prefix}-websocket-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.websocket_alb.id]
  subnets           = local.subnet_ids

  enable_deletion_protection = false

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-alb"
  })
}

# ALB Security Group
resource "aws_security_group" "websocket_alb" {
  name_prefix = "${local.name_prefix}-websocket-alb-"
  vpc_id      = local.vpc_id
  description = "Security group for WebSocket service ALB"

  ingress {
    description = "Health check endpoint"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    description = "To ECS tasks"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-alb-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ALB Target Group
resource "aws_lb_target_group" "websocket_service" {
  name        = "${local.name_prefix}-websocket-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = local.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-tg"
  })
}

# ALB Listener
resource "aws_lb_listener" "websocket_service" {
  load_balancer_arn = aws_lb.websocket_service.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.websocket_service.arn
  }
}

# ECS Service
resource "aws_ecs_service" "websocket_service" {
  name            = "${local.name_prefix}-websocket"
  cluster         = aws_ecs_cluster.speed_layer.id
  task_definition = aws_ecs_task_definition.websocket_service.arn
  desired_count   = var.websocket_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.websocket_service.id]
    assign_public_ip = true  # Required for Fargate tasks in public subnets
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.websocket_service.arn
    container_name   = "websocket-service"
    container_port   = 8080
  }

  # Wait for ALB to be ready
  depends_on = [aws_lb_listener.websocket_service]

  # Deployment configuration
  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }

  # Service discovery (optional, for future use)
  enable_execute_command = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-service"
  })

  lifecycle {
    ignore_changes = [desired_count]  # Allow auto-scaling to manage this
  }
}

# Auto Scaling Target
resource "aws_appautoscaling_target" "websocket_service" {
  count = var.enable_auto_scaling ? 1 : 0

  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.speed_layer.name}/${aws_ecs_service.websocket_service.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-websocket-scaling-target"
  })
}

# Auto Scaling Policy - CPU
resource "aws_appautoscaling_policy" "websocket_service_cpu" {
  count = var.enable_auto_scaling ? 1 : 0

  name               = "${local.name_prefix}-websocket-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.websocket_service[0].resource_id
  scalable_dimension = aws_appautoscaling_target.websocket_service[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.websocket_service[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = var.target_cpu_utilization
    scale_in_cooldown  = 300
    scale_out_cooldown = 300
  }
}
