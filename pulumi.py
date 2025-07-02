import pulumi
import pulumi_aws as aws
import json

# Get availability zones
azs = aws.get_availability_zones(state="available")

# Create VPC
vpc = aws.ec2.Vpc("chat-app-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_support=True,
    enable_dns_hostnames=True,
    tags={'Name': 'chat-app-vpc'}
)

# Create Internet Gateway
igw = aws.ec2.InternetGateway("chat-app-igw", 
    vpc_id=vpc.id,
    tags={'Name': 'chat-app-igw'}
)

# Create subnets in different availability zones
subnet_a = aws.ec2.Subnet("chat-subnet-a",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone=azs.names[0],
    map_public_ip_on_launch=True,
    tags={'Name': 'chat-subnet-a'}
)

subnet_b = aws.ec2.Subnet("chat-subnet-b",
    vpc_id=vpc.id,
    cidr_block="10.0.2.0/24",
    availability_zone=azs.names[1],
    map_public_ip_on_launch=True,
    tags={'Name': 'chat-subnet-b'}
)

# Create route table
route_table = aws.ec2.RouteTable("chat-rt",
    vpc_id=vpc.id,
    routes=[{"cidr_block": "0.0.0.0/0", "gateway_id": igw.id}],
    tags={'Name': 'chat-route-table'}
)

# Associate subnets with route table
aws.ec2.RouteTableAssociation("rta-a", 
    subnet_id=subnet_a.id, 
    route_table_id=route_table.id
)
aws.ec2.RouteTableAssociation("rta-b", 
    subnet_id=subnet_b.id, 
    route_table_id=route_table.id
)

# Security Group for chat app servers
sg = aws.ec2.SecurityGroup("chat-sg",
    vpc_id=vpc.id,
    description="Security group for chat app servers",
    ingress=[
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "tcp", "from_port": 80, "to_port": 80, "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "tcp", "from_port": 443, "to_port": 443, "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "tcp", "from_port": 8000, "to_port": 8000, "cidr_blocks": ["0.0.0.0/0"]},
        {"protocol": "icmp", "from_port": -1, "to_port": -1, "cidr_blocks": ["0.0.0.0/0"]}
    ],
    egress=[
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}
    ],
    tags={'Name': 'chat-security-group'}
)

# User data script to install Docker
user_data = '''#!/bin/bash
apt-get update
apt-get install -y docker.io dnsutils
systemctl start docker
systemctl enable docker
usermod -aG docker ubuntu


sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose

sudo chmod +x /usr/local/bin/docker-compose

'''

# Modified deployment approach:
# Instead of using IAM roles for S3 access, we'll deploy a simple health check app
# You will need to manually upload and deploy the application to the EC2 instances

# Create EC2 instances for chat app servers
chat_server_1 = aws.ec2.Instance("chat-server-1",
    instance_type="t2.micro",
    ami="ami-01811d4912b4ccb26",  # Ubuntu 20.04 LTS
    vpc_security_group_ids=[sg.id],
    subnet_id=subnet_a.id,
    key_name="jilan-key",
    user_data=user_data,
    tags={'Name': 'chat-server-1', 'Role': 'chat-server-1'}
)

chat_server_2 = aws.ec2.Instance("chat-server-2",
    instance_type="t2.micro",
    ami="ami-01811d4912b4ccb26",  # Ubuntu 20.04 LTS
    vpc_security_group_ids=[sg.id],
    subnet_id=subnet_b.id,
    key_name="jilan-key",
    user_data=user_data,
    tags={'Name': 'chat-server-2', 'Role': 'chat-server-2'}
)



# Create target group for HTTP chat app traffic
# Create target group for HTTP chat app traffic
http_tg = aws.lb.TargetGroup("chat-http-tg",
    port=80,
    protocol="HTTP",
    vpc_id=vpc.id,
    target_type="instance",
    health_check={
        "protocol": "HTTP",
        "port": "80",
        "path": "/",  
        "healthy_threshold": 2,
        "interval": 30,
        "timeout": 10,
        "unhealthy_threshold": 2,
        "matcher": "200",
    },
    stickiness={
        "enabled": True,
        "type": "lb_cookie",
        "cookie_duration": 86400,  # 24 hours in seconds (1-604800 seconds)
        "cookie_name": "AWSALB"    # Optional: custom cookie name
    },
    tags={'Name': 'chat-http-target-group'}
)

# Attach instances to target group
aws.lb.TargetGroupAttachment("chat-server-1-attachment",
    target_group_arn=http_tg.arn,
    target_id=chat_server_1.id,
    port=80
)

aws.lb.TargetGroupAttachment("chat-server-2-attachment",
    target_group_arn=http_tg.arn,
    target_id=chat_server_2.id,
    port=80
)



# Create Application Load Balancer
alb = aws.lb.LoadBalancer("chat-alb",
    load_balancer_type="application",
    internal=False,
    subnets=[subnet_a.id, subnet_b.id],
    security_groups=[sg.id],
    enable_deletion_protection=False,
    tags={'Name': 'chat-alb'}
)

# Create HTTP listener
http_listener = aws.lb.Listener("chat-http-listener",
    load_balancer_arn=alb.arn,
    port="80",
    protocol="HTTP",
    default_actions=[{
        "type": "forward", 
        "target_group_arn": http_tg.arn
    }]
)

# Security group for Redis EC2 instance
redis_sg = aws.ec2.SecurityGroup("redis-sg",
    vpc_id=vpc.id,
    description="Security group for Redis server",
    ingress=[
        {"protocol": "tcp", "from_port": 6379, "to_port": 6379, "security_groups": [sg.id]},
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]}
    ],
    egress=[
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}
    ],
    tags={'Name': 'redis-security-group'}
)

# User data script for Redis server
redis_user_data = '''#!/bin/bash
apt-get update
apt-get install -y docker.io dnsutils
systemctl start docker
systemctl enable docker
usermod -aG docker ubuntu

sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose

sudo chmod +x /usr/local/bin/docker-compose

# Create Redis container with persistence
mkdir -p /home/ubuntu/redis-data

cat > /home/ubuntu/docker-compose.yml << EOF

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --protected-mode no
    volumes:
      - ./redis-data:/data
    restart: always
EOF

cd /home/ubuntu
docker-compose up -d

echo "Redis server is running" > /home/ubuntu/redis-status.log
'''

# Create Redis EC2 instance
redis_server = aws.ec2.Instance("redis-server",
    instance_type="t2.micro",
    ami="ami-01811d4912b4ccb26",  # Ubuntu 20.04 LTS
    vpc_security_group_ids=[redis_sg.id],
    subnet_id=subnet_a.id,
    key_name="jilan-key",
    user_data=redis_user_data,
    tags={'Name': 'redis-server', 'Role': 'redis'}
)

# Export values
pulumi.export("chat_server_1_ip", chat_server_1.public_ip)
pulumi.export("chat_server_2_ip", chat_server_2.public_ip)
pulumi.export("chat_server_1_private_ip", chat_server_1.private_ip)
pulumi.export("chat_server_2_private_ip", chat_server_2.private_ip)
pulumi.export("alb_dns_name", alb.dns_name)
pulumi.export("target_group_arn", http_tg.arn)
pulumi.export("redis_endpoint", redis_server.private_ip)
pulumi.export("redis_server_ip", redis_server.public_ip)