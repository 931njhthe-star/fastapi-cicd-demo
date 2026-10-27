# FastAPI CI/CD Demo

아주 작은 FastAPI 앱을 GitHub Actions와 AWS에 연결해 자동 배포를 확인하는 예제입니다.

## 동작 흐름

- Pull request 또는 `main` 브랜치 push: `test` 성공 후 `build`에서 Docker 이미지 빌드
- `main` 브랜치 push: `build`가 ECR에 커밋 SHA 태그 이미지를 업로드하고, `deploy`가 해당 이미지를 SSM으로 EC2에 배포
- Pull request에서는 AWS 인증이나 배포 없이 Docker 이미지 빌드까지만 수행
- `/` 응답의 `version` 값에서 실제 배포된 커밋 SHA 확인
- `/health` 응답으로 배포 후 헬스 체크

## 실습 완료 기록

2026-10-26 기준으로 `main` 브랜치 push부터 EC2 배포까지 확인했습니다.

- GitHub Actions `test`: pytest와 Docker 이미지 빌드 검증 성공
- GitHub Actions `deploy`: OIDC로 AWS 인증, ECR 이미지 push, SSM을 통한 EC2 배포 성공
- 검증 커밋: `e527de30d09c39328d6d46b74be4c16aef57f57f`
- EC2에서 `curl http://127.0.0.1:8000/` 실행 시 앱 메시지와 해당 커밋의 `version` 응답 확인
- EC2에서 `curl http://127.0.0.1:8000/health` 실행 시 `{"status":"ok"}` 확인

새 배포를 검증할 때는 `/` 응답 메시지를 바꾸고 테스트의 기대값도 함께 수정한 뒤 `main`에 push합니다. Actions의 새 실행에서 `test`와 `deploy`가 모두 성공했는지 확인하고, EC2에서 다음 명령을 실행해 응답 메시지와 `version`이 새 커밋으로 바뀌었는지 확인합니다.

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
```

현재 Compose는 앱 포트를 EC2 내부 `127.0.0.1:8000`에만 바인딩합니다. Nginx와 공개 HTTP/HTTPS 연결은 이 실습에서 설정하지 않았으므로, 앱을 인터넷에서 직접 접속할 수 없는 것이 정상입니다.

## 로컬 실행

Python 3.12 이상을 사용합니다.

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
uvicorn app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000/` 또는 `http://127.0.0.1:8000/health`를 확인합니다. Docker로 확인하려면:

```bash
docker build --build-arg APP_VERSION=local -t fastapi-cicd-demo .
docker run --rm -p 8000:8000 fastapi-cicd-demo
```

## AWS와 GitHub 준비

기본 리전은 `ap-northeast-2`(서울), ECR 저장소 이름은 `fastapi-demo`입니다. 아래 예시는 Ubuntu 22.04/24.04 또는 Amazon Linux 2023 x86_64 EC2를 기준으로 합니다. `<...>` 표시는 본인 AWS 값으로 바꿔 입력하세요.

### 1. ECR 저장소 생성

AWS 콘솔에서 리전을 서울(`ap-northeast-2`)로 선택한 뒤 **Amazon ECR → Private registry → Repositories → Create repository**로 이동해 `fastapi-demo`라는 private 저장소를 만듭니다. 계정 ID와 저장소 URI를 확인합니다. URI 형식은 다음과 같습니다:

```text
<AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/fastapi-demo
```

### 2. EC2 인스턴스 프로파일 권한 설정

EC2는 인스턴스 프로파일을 통해 SSM에 연결하고 ECR에서 이미지를 내려받습니다. EC2 콘솔에서 **IAM role**을 붙이지 않고 진행하면 배포 단계가 실패합니다.

1. IAM 콘솔 → **Roles → Create role**에서 trusted entity type `AWS service`, use case `EC2`를 선택합니다.
2. `AmazonSSMManagedInstanceCore` 정책을 붙입니다.
3. **Add permissions → Create inline policy → JSON**에서 아래 정책을 추가합니다. `<AWS_ACCOUNT_ID>`는 12자리 계정 ID로 바꾸세요. 저장소 ARN만 이미지 읽기 대상으로 제한하고, ECR 로그인 토큰 조회는 AWS 요구사항상 `*` 리소스를 사용합니다.

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "GetEcrLoginToken",
         "Effect": "Allow",
         "Action": "ecr:GetAuthorizationToken",
         "Resource": "*"
       },
       {
         "Sid": "PullOnlyFastapiDemo",
         "Effect": "Allow",
         "Action": [
           "ecr:BatchCheckLayerAvailability",
           "ecr:BatchGetImage",
           "ecr:GetDownloadUrlForLayer"
         ],
         "Resource": "arn:aws:ecr:ap-northeast-2:<AWS_ACCOUNT_ID>:repository/fastapi-demo"
       }
     ]
   }
   ```

4. Role 이름을 예를 들어 `FastApiDemoEc2Role`로 지정해 생성합니다. EC2 콘솔에서 인스턴스를 선택하고 **Actions → Security → Modify IAM role**에서 이 Role을 연결합니다. 인스턴스 프로파일은 Role 생성 시 함께 만들어집니다.

### 3. 네트워크 및 EC2 생성

처음 설정하기 쉬운 구성은 EC2를 **public subnet**에 두고 인터넷으로 나가는 연결을 허용하는 것입니다. AWS 콘솔에서 **EC2 → Launch instance**를 열어 다음처럼 설정합니다:

- AMI: Ubuntu Server 22.04 LTS 또는 24.04 LTS
- 인스턴스 유형: 테스트용 `t3.micro` (무료 사용 여부와 비용은 계정/리전에 따라 다를 수 있음)
- Network: 인터넷 게이트웨이(IGW)로 나가는 경로가 있는 public subnet, public IPv4 자동 할당 활성화
- IAM instance profile: 앞에서 만든 `FastApiDemoEc2Role`
- Security group inbound:
  - SSH `22`: 처음 SSH 접속을 쓸 경우에만 **My IP**로 제한. 설정이 끝나면 규칙 삭제 권장
  - HTTP `80`, HTTPS `443`: Nginx를 외부에 서비스할 때만 추가. 테스트할 때는 본인 IP만 허용하는 편이 안전합니다.
  - 앱 포트 `8000`은 열지 마세요. Compose가 `127.0.0.1:8000`에만 바인딩합니다.
- Outbound: 기본 허용(모든 IPv4 목적지). Docker 패키지 설치, SSM, ECR 접근에 필요합니다.

public subnet은 route table에 `0.0.0.0/0 → Internet Gateway` 경로가 있어야 합니다. 보안 그룹의 outbound HTTPS(443)를 막지 마세요. private subnet을 사용하려면 NAT Gateway 또는 다음 VPC endpoints가 추가로 필요합니다: `ssm`, `ssmmessages`, `ec2messages`(리전/SSM 구성에 따라), `ecr.api`, `ecr.dkr`, 그리고 ECR 이미지 layer 다운로드를 위한 S3 gateway endpoint. NAT Gateway는 비용이 발생할 수 있습니다.

### 4. EC2에 Docker, Compose, AWS CLI, SSM Agent 설치

SSM으로 EC2에 접속하는 방법은 EC2 콘솔 → **Connect → Session Manager → Connect**입니다. Role이 연결되고 인스턴스가 SSM에 등록될 때까지 몇 분 걸릴 수 있습니다.

#### Amazon Linux 2023인 경우

현재 EC2 AMI가 Amazon Linux 2023이면 Ubuntu용 `apt-get` 명령은 실행하지 마세요. Docker 설치 후 Compose 플러그인을 추가합니다. 아래 명령은 `t3.micro` 등의 x86_64 인스턴스용입니다:

```bash
sudo dnf update -y
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo docker version

sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL \
  https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
sudo docker compose version
```

`docker compose version`에서 Compose 버전이 출력되면 준비된 것입니다. ARM 인스턴스(예: `t4g`)라면 다운로드 주소의 `x86_64`를 `aarch64`로 바꿉니다. Amazon Linux 2023 AMI에는 보통 AWS CLI와 SSM Agent가 이미 포함되어 있으므로 다음으로 확인하고, `aws configure`에 개인 액세스 키를 입력하지 마세요:

```bash
aws --version
aws sts get-caller-identity
sudo systemctl status amazon-ssm-agent --no-pager
```

#### Ubuntu인 경우

Docker 공식 Ubuntu 저장소에서 Docker Engine과 Compose 플러그인을 설치합니다:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl unzip
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

AWS CLI v2 설치 명령은 인스턴스 아키텍처에 맞춰 하나만 실행합니다. 일반적인 `t3` 계열은 x86_64입니다:

```bash
# x86_64 (예: t3)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"
unzip -q /tmp/awscliv2.zip -d /tmp
sudo /tmp/aws/install
```

ARM 인스턴스(예: `t4g`)라면 다운로드 URL에서 `linux-x86_64`를 `linux-aarch64`로 바꿉니다. 설치 확인:

```bash
aws --version
aws sts get-caller-identity
```

`get-caller-identity`는 EC2 인스턴스 Role을 보여야 합니다. 이 EC2에 `aws configure`로 사용자 액세스 키를 저장하지 마세요.

SSM Agent는 Ubuntu에서 snap으로 설치/실행합니다:

```bash
if ! snap list amazon-ssm-agent >/dev/null 2>&1; then
  sudo snap install amazon-ssm-agent --classic
fi
sudo systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service
sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent.service --no-pager
```

SSM 연결이 안 되면 인스턴스 Role에 `AmazonSSMManagedInstanceCore`가 연결됐는지, public subnet/인터넷 또는 SSM VPC endpoints가 있는지, outbound HTTPS 443이 허용됐는지 확인합니다. EC2 콘솔의 **Systems Manager → Fleet Manager**에서 인스턴스가 관리형 노드로 나타나야 합니다.

### 5. 배포 파일 설치 및 확인

EC2의 Session Manager 터미널에서 다음 파일을 만듭니다. `nano` 편집기에서 붙여넣은 뒤 저장합니다 (`Ctrl+O`, Enter, `Ctrl+X`).

```bash
sudo mkdir -p /opt/myapp
sudo nano /opt/myapp/compose.yaml
```

내용:

```yaml
services:
  app:
    image: ${IMAGE_URI}
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
```

배포 스크립트를 만듭니다:

```bash
sudo nano /opt/myapp/deploy.sh
```

내용:

```bash
#!/usr/bin/env bash
set -euo pipefail

IMAGE_URI="${1:?Usage: deploy.sh <image-uri>}"
AWS_REGION="${AWS_REGION:-ap-northeast-2}"
REGISTRY="${IMAGE_URI%%/*}"

aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$REGISTRY"

cd /opt/myapp
IMAGE_URI="$IMAGE_URI" docker compose pull app
IMAGE_URI="$IMAGE_URI" docker compose up -d app

curl --fail --silent --show-error \
  --retry 10 --retry-delay 2 --retry-connrefused --retry-all-errors \
  http://127.0.0.1:8000/health
```

실행 권한을 설정하고 Docker가 실행되는지 확인합니다:

```bash
sudo chmod +x /opt/myapp/deploy.sh
sudo docker info
```

SSM Run Command는 root로 실행되므로 `sudo` 없이 Docker 명령을 사용할 수 있습니다. 처음 배포 전까지 컨테이너가 없어서 `/health`가 응답하지 않는 것은 정상입니다.

### 6. GitHub Actions의 AWS OIDC 설정

AWS IAM에서 GitHub OIDC Provider(`https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`)를 등록합니다. GitHub용 IAM Role trust policy의 `sub`는 본인 GitHub 조직/사용자와 저장소의 `main` 브랜치로 제한하세요. 예시 claim은 다음과 같지만, GitHub 저장소의 실제 OIDC claim 형식을 확인해 적용해야 합니다:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:<GITHUB_OWNER>/<GITHUB_REPOSITORY>:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

GitHub Role에는 해당 ECR 저장소로 이미지 업로드하는 권한 및 지정 EC2의 SSM 명령 실행/결과 조회 권한만 부여합니다. GitHub 저장소의 **Settings → Secrets and variables → Actions → Variables**에 다음 변수를 등록합니다:

- `AWS_ROLE_ARN`: GitHub Actions가 Assume할 IAM Role ARN
- `EC2_INSTANCE_ID`: 배포 대상 EC2 인스턴스 ID

### 7. Nginx 연결 및 배포 확인

Nginx가 설치되어 있다면 요청을 `http://127.0.0.1:8000`으로 전달하도록 설정하고, EC2 보안 그룹에는 Nginx가 사용하는 포트만 공개합니다. 애플리케이션 포트 8000을 인터넷에 직접 공개하지 않습니다. 예를 들어 Nginx 사이트 설정의 `server` 블록에 다음 location을 둘 수 있습니다:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

모든 설정 후 변경사항을 `main`에 push합니다. Actions에서 테스트 → ECR 업로드 → SSM 배포가 성공하는지 확인한 뒤 `http://<EC2_PUBLIC_IP>/` 응답의 `version` 및 `/health` 응답을 확인합니다.

IAM 정책은 최소 권한으로 제한하세요. IAM의 SSM 리소스 제약 및 GitHub OIDC `sub` 조건은 계정과 저장소 설정에 맞게 확인해야 합니다.

## 참고

- PR에서는 AWS 인증 및 배포를 하지 않습니다.
- 배포 실패 시 Actions에 실패가 표시되지만, 이 예제에는 자동 롤백이나 무중단 배포가 없습니다.
- 앱에서 비밀값이 필요해지면 EC2에 별도로 안전하게 제공하세요. `.env`나 AWS 자격 증명을 저장소에 커밋하지 마세요.
