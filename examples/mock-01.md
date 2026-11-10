# 작은 운영 클러스터 연습

직접 창작한 UI 체험용 모의고사입니다. 실제 시험 문제나 덤프가 아닙니다.

## Q1
 domain: Troubleshooting
 weight: 40

컨텍스트: k8s-c1 · 시작 호스트: controlplane

team-a 네임스페이스의 ledger Deployment가 정상 응답하지 않습니다.
현재 Pod 상태와 이벤트를 조사하고 애플리케이션을 복구하세요.

- Deployment 이름과 replica 수를 유지하세요.
- 모든 replica가 Ready인지 확인하세요.
- 조사한 내용을 문항 메모에 남겨도 됩니다.

## Q2
 domain: Services & Networking
 weight: 35

컨텍스트: k8s-c1 · 시작 호스트: controlplane

team-b 네임스페이스의 atlas Deployment를 클러스터 내부에서 접근할 수 있게 하세요.

- Service 이름은 atlas-internal입니다.
- Service 포트는 80, 애플리케이션 수신 포트는 8080입니다.
- 기존 Pod의 label을 변경하지 마세요.
- Service의 대상이 연결되는지 확인하세요.

## Q3
 domain: Storage
 weight: 25

컨텍스트: k8s-c1 · 시작 호스트: controlplane

archive 네임스페이스에 데이터를 보관할 PVC와 Pod를 만드세요.

- PVC 이름은 records, 요청 용량은 1Gi, 접근 모드는 ReadWriteOnce입니다.
- 기존 StorageClass standard를 사용하세요.
- Pod 이름은 reader, 이미지는 busybox:1.36입니다.
- 볼륨을 /records에 마운트하고 Pod가 실행 상태를 유지하게 하세요.
- PVC가 Bound인지 확인하세요.
