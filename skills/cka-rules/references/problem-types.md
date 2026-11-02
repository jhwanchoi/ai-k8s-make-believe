# CKA 출제 유형 카탈로그

CKA 커리큘럼(2025 개편) 역량 항목을 문제 유형으로 풀어 쓴 것이다. grader 가 새 문제를 만들 때, 그리고 붙여넣은 문제의 환경을 만들 때 참고한다.

- 특정 모의고사나 시험 문제를 옮기지 않는다. 이름, 네임스페이스, 값, 고장 원인은 매번 새로 정한다.
- 2025 개편 이후 Gateway API, Helm, Kustomize, CRD 와 Operator, 워크로드 오토스케일링 비중이 커졌다. 최신 범위는 https://github.com/cncf/curriculum 을 따른다.
- "함정" 칸은 공식 문서에도 나오는 흔한 실수다. 환경에 재현해 두고 1, 2단계 힌트 소재로 쓴다. 정답을 그대로 말하지 않는다.
- "시뮬레이션" 칸이 약함이면 결과 출력에 `(추정)` 을 붙인다.

## Workloads & Scheduling

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| Pod 스펙 작성 (멀티 컨테이너, 볼륨 공유, downward API) | 컨테이너별 이름과 이미지, 볼륨 마운트, `fieldRef` | env `valueFrom` 문법, 마운트 경로 불일치 | 보통 |
| sidecar (native sidecar 포함) | `initContainers` + `restartPolicy: Always` 또는 일반 컨테이너, 공유 볼륨 | 네임스페이스 누락, 예시 YAML 값을 그대로 둠 | 보통 |
| Deployment 생성, 이미지 업데이트, 롤백 | replicas, image, rollout 이력 | 문제가 지정한 방식(`kubectl apply` 등)을 따르지 않음 | 쉬움 |
| ConfigMap, Secret 주입 | env, envFrom, volume 중 요구한 방식 | `kubectl set env --from=configmap/<cm>` 를 모름 | 쉬움 |
| HPA (resource, custom metric, behavior) | `autoscaling/v2`, metric 종류와 target, min/max, `spec.behavior` | 템플릿 파일의 이름과 대상을 안 바꿈, `Pods` 와 `Object` metric 혼동 | 보통 |
| VPA | `targetRef`, `updatePolicy.updateMode` | CRD 가 설치돼 있는지 먼저 확인 | 보통 |
| PriorityClass | value, Pod `priorityClassName` | Pod spec 은 대부분 수정 불가라 재생성 필요 | 쉬움 |
| taint, toleration, nodeSelector, affinity | 노드 taint key/value/effect, Pod 가 실제로 스케줄된 노드 | 문제의 값 대신 예시 값을 씀 | 약함 |
| static pod | 해당 노드의 `staticPodPath`, mirror Pod 이름 `<name>-<node>` | 다른 노드에 만듦, kubelet 설정의 경로 확인 생략 | 보통 |

## Services & Networking

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| Service (ClusterIP, NodePort) | 이름, 포트, selector 가 Pod 를 고름, nodePort | 손으로 쓴 selector 가 Pod label 과 다름, `kubectl expose` 로는 nodePort 지정 불가 | 쉬움 |
| Ingress | host, path, `pathType`, backend, `ingressClassName` | default IngressClass 가 없을 때 class 를 빠뜨려 라우팅 안 됨 | 약함 |
| Gateway, HTTPRoute | `gatewayClassName`, listener (HTTP, HTTPS, `tls.certificateRefs`), `parentRefs`, `backendRefs[].weight` | 기존 listener 를 덮어씀, TLS 필드 위치 | 보통 |
| NetworkPolicy | podSelector, policyTypes, ingress/egress 규칙, namespaceSelector | 기존 default-deny 와 공존, namespaceSelector 와 podSelector 결합 의미 | 약함 |
| DNS, 서비스 디스커버리 | Service, Pod DNS 이름 조회 | Pod DNS 이름 형식 | 약함 |

## Storage

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| PV, PVC | capacity, accessModes, storageClassName, `status.phase: Bound` | accessModes 나 storageClassName 불일치로 Pending, PVC spec 은 재생성 필요 | 보통 |
| StorageClass | provisioner, `volumeBindingMode`, `allowVolumeExpansion`, default annotation | `storageclass.kubernetes.io/is-default-class` 위치 | 쉬움 |

## Cluster Architecture, Installation & Configuration

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| RBAC (Role, ClusterRole, Binding, ServiceAccount) | verbs, resources, subjects, `serviceAccountName` | 클러스터 범위 리소스엔 ClusterRole, `--serviceaccount=<ns>:<name>` 형식 | 쉬움 |
| 사용자 인증서 (CSR) | `signerName`, `usages`, Approved, 권한 확인 | CSR 은 클러스터 범위 리소스 | 보통 |
| 노드 준비 (런타임 설치, 커널 파라미터, 서비스) | 패키지, systemd 서비스 active + enabled, sysctl 영구화 | 재부팅 후 유지되게 파일에 써야 함 | 보통 |
| kubeadm 클러스터 구성 | `kubeadm-config` ConfigMap, 인증서, 업그레이드 절차 | 클러스터 단위 값과 노드 단위 값 혼동 | 보통 |
| etcd 백업과 복구 | 스냅샷 경로, 엔드포인트, 인증서 플래그 | 인증서 경로, 복구 후 data-dir 반영 | 보통 |
| CRD, Operator | CRD 조회, CR 작성 | CRD 설치 여부 확인 | 쉬움 |
| Helm, Kustomize | repo, install/upgrade/uninstall, 차트 버전, `kubectl apply -k` | 버전 확인 없이 upgrade, 네임스페이스 누락 | 약함 |

## Troubleshooting

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| 워크로드 기동 실패 | Pod Running, 원인 수정 | `describe` 이벤트 확인, Pod spec 불변 | 보통 |
| 컨트롤 플레인 컴포넌트 장애 | kube-system Pod Running, static pod manifest 수정 | 증상이 보이는 곳과 원인 컴포넌트가 다름 | 보통 |
| kubelet, 노드 장애 | 노드 Ready, kubelet active | `journalctl -u kubelet`, 설정 파일 경로 | 보통 |
| kubeconfig, 인증 오류 | 지정한 kubeconfig 로 접속 성공 | server 주소와 포트, 인증서 항목 | 쉬움 |
| 서비스, 네트워크 연결 장애 | endpoints, DNS, NetworkPolicy | selector, targetPort | 약함 |
