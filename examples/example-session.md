# 예시 세션

직접 만든 연습문제 하나를 처음부터 끝까지 푼 흐름입니다. 출력은 시뮬레이션이라 실제로 써 보면 문제와 상황에 따라 조금씩 달라집니다.

## 1. 문제 불러오기

```
/ai-k8s-make-believe:cka-load prod 네임스페이스의 web Deployment를 web-svc라는 ClusterIP Service로 노출하라. Service 포트는 80, 컨테이너 포트는 8080이다.
```

> **q01-web-svc** (Services & Networking, curriculum 2025+)
>
> prod 네임스페이스의 web Deployment를 web-svc라는 ClusterIP Service로 노출하라. Service 포트는 80, 컨테이너 포트는 8080이다.
>
> 시작 위치: `host=controlplane`, `ctx=k8s-c1`. `/ai-k8s-make-believe:cka <명령>`이나 `$ <명령>`으로 풀고 다 풀면 `/ai-k8s-make-believe:cka-submit` 하세요.

## 2. 풀기

```console
# [SIM] host=controlplane ctx=k8s-c1
$ kubectl get deploy,pod -n prod --show-labels
NAME                  READY   UP-TO-DATE   AVAILABLE   AGE   LABELS
deployment.apps/web   2/2     2            2           14m   app=web

NAME                       READY   STATUS    RESTARTS   AGE   LABELS
pod/web-6d4cf56db6-8xkqp   1/1     Running   0          14m   app.kubernetes.io/name=web,pod-template-hash=6d4cf56db6
pod/web-6d4cf56db6-tm2zr   1/1     Running   0          14m   app.kubernetes.io/name=web,pod-template-hash=6d4cf56db6
```

Deployment 라벨을 보고 YAML을 직접 씁니다.

```console
# [SIM] host=controlplane ctx=k8s-c1
$ cat <<EOF > svc.yaml
apiVersion: v1
kind: Service
metadata:
  name: web-svc
  namespace: prod
spec:
  selector:
    app: web
  ports:
  - port: 80
    targetPort: 8080
EOF
$ kubectl apply -f svc.yaml
service/web-svc created
```

실제 클러스터처럼 apply는 아무 문제 없이 성공합니다.

## 3. 첫 제출 (오답)

```
/ai-k8s-make-believe:cka-submit
```

```console
# [SIM] host=controlplane ctx=k8s-c1
$ kubectl get endpoints web-svc -n prod
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME      ENDPOINTS   AGE
web-svc   <none>      40s
```

> 점수 2/4. Service는 만들어졌는데 트래픽을 받을 대상이 없습니다. Service가 어떤 Pod를 고르는지 다시 확인해 보세요. (힌트 1/3)

정답이나 어느 루브릭 항목이 틀렸는지는 아직 알려주지 않습니다. 한 번 더 틀리면 원인을 좁히는 진단 출력과 함께 더 구체적인 위치를 짚어 줍니다.

## 4. 고치고 다시 제출

```console
# [SIM] host=controlplane ctx=k8s-c1
$ kubectl delete svc web-svc -n prod
service "web-svc" deleted
$ kubectl expose deploy web -n prod --name web-svc --port 80 --target-port 8080
service/web-svc exposed
$ kubectl get endpointslice -n prod -l kubernetes.io/service-name=web-svc
NAME            ADDRESSTYPE   PORTS   ENDPOINTS                 AGE
web-svc-7xq2d   IPv4          8080    10.244.1.12,10.244.2.7   5s
```

```
/ai-k8s-make-believe:cka-submit
```

> **정답입니다.** 점수 4/4
>
> 실전 피드백
> - 처음부터 `kubectl expose`를 썼으면 한 줄로 끝났습니다. expose는 Deployment의 selector를 그대로 가져가서 이번 같은 라벨 실수가 생기지 않습니다.
> - `--show-labels`의 LABELS 열은 Deployment 자신의 라벨입니다. Pod를 고르는 기준은 `spec.selector`이니 `kubectl get deploy web -n prod -o jsonpath='{.spec.selector}'`로 확인하세요.
> - Service를 만든 뒤 바로 endpoints를 확인하는 습관을 들이면 시험에서 조용한 실패를 놓치지 않습니다.
>
> 오답 노트에 기록하고 문제 폴더를 `.cka/archive/`로 옮겼습니다. 다음 문제는 `/ai-k8s-make-believe:cka-load`로 불러오세요.

`.cka/wrong-notes.md`에는 이렇게 남습니다.

```markdown
## 2026-11-02 q01-web-svc (정답, 오답 1회)
- 문제: prod의 web Deployment를 80 포트 ClusterIP Service로 노출
- 실수: Deployment 라벨(app=web)을 Pod selector로 씀
- 에러: `web-svc   <none>   40s` (endpoints 비어 있음)
- 교훈: selector는 spec.selector에서 확인하고 만든 뒤 바로 endpoints 확인
```
