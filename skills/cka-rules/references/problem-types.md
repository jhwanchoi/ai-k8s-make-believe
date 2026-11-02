# CKA 출제 유형 카탈로그 (2025 개편 이후)

2025 개편 이후 모의고사 37문항을 풀어 보고 뽑은 유형이다. grader 가 새 문제를 만들 때 참고한다. 문장은 매번 새로 쓰고, 이름, 네임스페이스, 값은 바꾼다.

- 관찰: Gateway API, HPA/VPA, Helm, 트러블슈팅 비중이 크다. 단독 etcd 백업/복구, kubeadm 업그레이드는 37문항 중 한 번도 없었다.
- "함정" 칸은 1, 2단계 힌트의 소재다. 정답을 그대로 말하지 말고 방향과 위치만 짚는다.
- "시뮬레이션" 칸이 약함이면 결과 출력에 `(추정)` 을 붙인다.

## Workloads & Scheduling

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| 멀티 컨테이너 Pod (emptyDir 공유, 로그 sidecar, downward API env) | 컨테이너 이름, 이미지, `fieldRef: spec.nodeName`, 같은 볼륨 마운트 | env `valueFrom.fieldRef` 문법, 마운트 경로 불일치 | 보통 |
| native sidecar Deployment | `initContainers` + `restartPolicy: Always`, 공유 볼륨, 컨테이너 이름 | 이름, 네임스페이스 누락, 예시 YAML 의 이미지를 그대로 둠 | 보통 |
| Deployment 생성과 rolling update | replicas, 이미지 버전 변경, `kubectl apply` 지정 시 그 방식 | `set image` 를 썼는데 apply 를 요구한 경우 | 쉬움 |
| ConfigMap 을 env 로 주입 | ConfigMap 키, Deployment env (`envFrom` 또는 `valueFrom`) | `kubectl set env --from=configmap/<cm>` 를 모름 | 쉬움 |
| HPA (cpu, memory 사용률) | `autoscaling/v2`, target 종류와 값, min/max, 이름과 대상 | 주어진 YAML 의 이름, 대상 Deployment 를 안 바꿈 | 보통 |
| HPA behavior | `behavior.scaleDown.stabilizationWindowSeconds` | 필드 위치 (`spec.behavior`) | 보통 |
| HPA custom metric | `type: Pods` + `AverageValue` (요구가 "pod 평균" 일 때) | `Object` 타입이나 metric 이름 오타 | 보통 |
| VPA | `autoscaling.k8s.io/v1`, `targetRef`, `updatePolicy.updateMode` | CRD 가 설치돼 있는지 먼저 확인 | 보통 |
| PriorityClass 적용 | value, Pod `priorityClassName`, Pod 재생성 | Pod spec 은 대부분 수정 불가, `priority` 필드를 지우지 않음 | 쉬움 |
| taint 와 toleration | taint key/value/effect 정확히, toleration 있는 Pod 만 해당 노드 | 문제에서 준 key/value 대신 예시 값을 씀 | 약함 |
| static pod | `/etc/kubernetes/manifests/<file>.yaml` (해당 노드), Pod 이름 `<name>-<node>` | 엉뚱한 노드에 만듦 | 보통 |

## Services & Networking

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| Pod/Deployment expose (ClusterIP) | 이름, 포트, selector 가 Pod 를 고름 | 손으로 쓴 selector 가 Pod label 과 다름 | 쉬움 |
| 고정 nodePort Service | `type: NodePort`, `nodePort` 값 | `expose` 로는 nodePort 지정 불가, dry-run YAML 수정 필요 | 쉬움 |
| Ingress | host, path, `pathType`, backend service/port, `ingressClassName` | `ingressClassName` 누락으로 404 | 약함 |
| Gateway 생성 | `gatewayClassName`, listener name/protocol/port | 요구하지 않은 hostname 추가 | 보통 |
| Gateway HTTPS listener | `protocol: HTTPS`, port 443, hostname, `tls.certificateRefs` | 기존 HTTP listener 를 덮어씀 vs 추가 요구 구분 | 보통 |
| HTTPRoute 가중치 분할 | `parentRefs`, `backendRefs[].weight` | weight 합, 포트 누락 | 약함 |
| NetworkPolicy 작성 (default-deny 와 공존) | podSelector, ingress port, 기존 정책 유지 | `from: [{}]` 처리, 기존 정책 삭제 | 약함 |
| NetworkPolicy 고르기 (주어진 파일 중) | 가장 제한적인 정책 하나만 적용 | namespaceSelector 라벨 의미 오해 | 약함 |
| DNS 확인 결과 저장 | busybox 이미지로 `nslookup`, 지정 경로에 출력 저장 | 버전 지정 이미지 (`busybox:1.28`) 무시 | 약함 |

## Storage

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| PV hostPath | capacity, accessModes, hostPath | 단위 (`Mi`, `Gi`) | 쉬움 |
| StorageClass | provisioner, `volumeBindingMode`, `allowVolumeExpansion`, 기본 클래스 annotation | `storageclass.kubernetes.io/is-default-class: "true"` 위치 | 쉬움 |
| PVC 바인딩 트러블슈팅 | PVC 가 Bound, PV 는 수정 금지 | accessModes, storageClassName, 용량 불일치. PVC 는 재생성 필요 | 보통 |

## Cluster Architecture, Installation & Configuration

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| 노드 준비: 컨테이너 런타임 패키지 설치 | `.deb` 설치, 서비스 running + enabled | `enable --now` 로 둘 다 처리 | 보통 |
| 노드 준비: sysctl 영구 설정 | 값 적용 + 재부팅 후 유지 (`/etc/sysctl.d/*.conf` 또는 `/etc/sysctl.conf`) | `sysctl -w` 만 하고 파일에 안 씀 | 보통 |
| kubeadm 설정 조회 | `kubeadm-config` ConfigMap 의 `podSubnet` 을 파일로 | 노드별 `podCIDR` 과 혼동 | 쉬움 |
| CRD 조회 결과 저장 | 관련 CRD 이름만 파일에 | 출력 형식 (이름만, 한 줄씩) | 쉬움 |
| RBAC: SA + ClusterRole + Binding + Pod | 각 이름, verb/resource, `serviceAccountName` | binding 의 `--serviceaccount=<ns>:<name>` 형식 | 쉬움 |
| RBAC: 사용자 CSR 승인 + Role | CSR `signerName: kubernetes.io/kube-apiserver-client`, Approved, Role/RoleBinding, `auth can-i` | CSR 은 클러스터 범위, base64 한 줄 처리 | 보통 |
| Helm: repo update + upgrade | 릴리스 차트 버전 | repo 이름, 버전 값을 확인하지 않고 씀 | 약함 |
| Helm: 취약 이미지 릴리스 찾아 삭제 | `helm list -A`, manifest 에서 이미지 검색, uninstall | 네임스페이스 지정 누락 | 약함 |
| Helm: 로컬 차트 검증 후 교체 설치 | `helm lint`, 새 릴리스 install, 옛 릴리스 uninstall | 검증 단계 생략 | 약함 |

## Troubleshooting

| 유형 | 채점 포인트 | 함정 | 시뮬레이션 |
|---|---|---|---|
| Pod 기동 실패 (initContainer command 오타) | Pod Running | Pod spec 수정 불가, YAML 로 뽑아 지우고 재생성 | 보통 |
| kubeconfig 오류 (API 서버 포트 등) | 파일 수정 후 `kubectl --kubeconfig` 동작 | 기본 포트 6443 | 쉬움 |
| Deployment 가 스케일되지 않음 (controller-manager static pod 오타) | replicas 반영, kube-system 컨트롤 플레인 Pod Running | 증상은 Deployment, 원인은 control plane. `describe` 이벤트의 exec 오류 | 보통 |
| PVC Pending | 위 Storage 참고 | | 보통 |
