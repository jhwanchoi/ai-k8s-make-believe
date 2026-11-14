# CKA 기출/복기 자료 정리 (2026-10 기준)

> 이 문서는 외부 자료의 링크 목록입니다. 문제 원문은 이 저장소에 넣지 않습니다. 실제 시험 문제를 그대로 옮긴 덤프는 쓰지 마세요([README](../README.md) 참고). 각 자료의 라이선스와 내용은 원래 출처에서 확인하세요.

2025년 2월 개편 이후 나온 복기 자료는 거의 같은 17문항 안팎의 문제 풀로 모입니다. 그래서 '상' 등급 자료 몇 개만 풀어도 출제 범위 대부분을 다룹니다.

링크는 전부 열어서 실제 문제가 들어 있는지 확인했습니다. 날짜는 블로그는 작성일, GitHub는 마지막 push 날짜입니다.

> 전부 응시자 복기나 재구성 자료라서 리소스 이름이나 값은 실제 시험과 다릅니다. 시험 문제 원문을 공유하면 LF 응시 약관(NDA)에 걸릴 수 있습니다.

## 추천 순서

1. vj2201 저장소 17문항을 Killercoda playground에서 반복
2. sunrise-min, kangmihye 글로 한국어 풀이와 함정 확인
3. 응시권에 포함된 killer.sh 2회

## 개편 후 공통 출제 범위 (자료 5개 이상에서 일치)

- 설치/런타임: cri-dockerd 설치(dpkg, sysctl), CNI 설치(Calico나 Flannel, NetworkPolicy 지원 조건)
- Helm/CRD: ArgoCD를 helm template로 렌더링(CRD 제외), cert-manager CRD 목록과 kubectl explain 결과를 파일로 저장
- 스케줄링: PriorityClass(최고값-1, 적용 후 rollout), WordPress 리소스를 노드 자원 기준 3등분(initContainer 포함), taint/toleration
- 워크로드: sidecar와 emptyDir로 로그 수집, HPA(scaleDown stabilization 설정)
- 네트워크: Ingress를 Gateway/HTTPRoute로 전환(TLS 포함), Ingress 생성, NetworkPolicy 3개 중 맞는 것 고르기, NodePort로 expose, ConfigMap에서 TLSv1.3만 허용
- 스토리지: MariaDB용 PVC 복구(기존 PV 재사용), 기본 StorageClass 만들기(WaitForFirstConsumer)
- 트러블슈팅: etcd 주소가 틀어져 kube-apiserver가 안 뜨는 상황 복구

## 상: 개편 후 범위와 일치하고 풀이나 실습 환경까지 있음

| 자료 | 날짜 | 내용 | 링크 |
|---|---|---|---|
| vj2201/CKA-PREP-2025-v2 (228★) | 2026-10 | Killercoda 실습 17문항. 문제마다 LabSetUp과 풀이, 위 범위와 1:1 | https://github.com/vj2201/CKA-PREP-2025-v2 |
| CameronMetcalfe22/CKA-PREP (100★) | 2026-09 | 17문항, validate.sh, 문항마다 해설 영상 | https://github.com/CameronMetcalfe22/CKA-PREP |
| IT Kiddie 유튜브 "CKA EXAM 2026" | 2026 | 위 두 저장소의 원본 해설 영상 | https://www.youtube.com/playlist?list=PLkDZsCgo3Isr4NB5cmyqG7OZwYEx5XOjM |
| markdjones82/CKA-PREP-2025-v2 (158★) | 2026-06 | vj2201 fork, Q18·Q19 추가 19문항, 검증/정리 스크립트 | https://github.com/markdjones82/CKA-PREP-2025-v2 |
| gkeskar/CKA2025 real-question-bank | 2025-09 | 합격자가 정리한 15문항, 파일명이 위 범위와 일치 | https://github.com/gkeskar/CKA2025/tree/main/real-question-bank |
| sunrise-min 티스토리 "2025 CKA 시험 준비 핵심 요약" | 2025-05-01 | 한국어 14문항 이상, 거의 모든 문항에 YAML이나 명령어 | https://sunrise-min.tistory.com/entry/2025-CKA-%EC%8B%9C%ED%97%98-%EC%A4%80%EB%B9%84-%ED%95%B5%EC%8B%AC-%EC%9A%94%EC%95%BD |

## 중: 복기는 맞지만 풀이가 일부만 있거나, 직접 만든 문제

| 자료 | 날짜 | 내용 | 링크 |
|---|---|---|---|
| theplatformlab (550★) | 2026-10 | 직접 설계한 실습 32개, 모의고사 2회(각 15문항, 해설). 기출 아님 명시 | https://github.com/theplatformlab/CKA-Certified-Kubernetes-Administrator |
| techiescamp PRACTICE_QUESTIONS.md (1000★) | 2026-10 | 커리큘럼별 35문항, 직접 만든 문제 | https://github.com/techiescamp/cka-certification-guide/blob/main/PRACTICE_QUESTIONS.md |
| anouarharrou "CKA Simulations Exams Q&A" | 2026-09 | 복기형 15문항, 풀이 일부. Gateway v1beta1 등 옛 버전 섞임 | https://github.com/anouarharrou/The-Ultimate-CKA-Guide/blob/main/My%20Note/CKA%20Simulations%20Exams%20Q%26A.md |
| sriramg-aivar/cka-labs (0★) | 2026-09 | 같은 범위 17개 시나리오, run/check/reset 스크립트 | https://github.com/sriramg-aivar/cka-labs |
| TCS_CKA_2026_Exam_Scenarios (0★) | 2026-09 | 같은 범위 16개 시나리오 | https://github.com/The-Cyber-Sidekick/TCS_CKA_2026_Exam_Scenarios |
| tiaz.dev | 2026-03-13 | 가장 최근 복기(2026년 응시), 14문항 목록만, 풀이 없음 | https://tiaz.dev/k8s/1 |
| Medium kangmihye "CKA 2025 풀이노트" | 2025-12-29 | 한국어 10주제, 실제 명령어와 출력, 틀리기 쉬운 부분 위주 | https://medium.com/@kangmihye/cka-2025-%EC%98%A4%EB%8B%B5%EB%85%B8%ED%8A%B8-82a048e39ccd |
| velog new_blank | 2025-10-19 | 16문항 복기(46점 불합격 후 71점 합격), 풀이 일부 | https://velog.io/@new_blank/CKA-%ED%95%A9%EA%B2%A9-%ED%9B%84%EA%B8%B0-%EB%B0%8F-%EA%B8%B0%EC%B6%9C%EB%AC%B8%EC%A0%9C |
| ViktorUJ/cks CKA mock 01/02 (1634★) | 2025-09 | AWS에 terraform으로 실제 클러스터, 자동 채점. 기출 아님, 시뮬레이터로 가장 충실 | https://github.com/ViktorUJ/cks/tree/master/tasks/cka/mock |
| velog caesars000 | 2025-08-20 | 11주제 중 6개 상세 풀이(ArgoCD, Gateway TLS, cri-dockerd, PriorityClass 등) | https://velog.io/@caesars000/CKA-%EC%8B%9C%ED%97%98-%ED%9B%84%EA%B8%B0 |

## 하: 개편 전 자료, 오류 있음, 또는 내용 미검증

| 자료 | 날짜 | 내용 | 링크 |
|---|---|---|---|
| Medium "Real CKA Exam Question N of 17" | 2026-03 | 풀이 오류(GatewayClass 이름 불일치, TLS listener 누락), Udemy 홍보 | https://medium.com/@tradingcontentdrive/real-cka-exam-question-14-of-17-migrating-from-ingress-to-gateway-api-5cf85da1a41b |
| DevOpsCertification 유튜브 "2025 CKA Real Questions" | - | 재생목록 존재만 확인, 내용 못 봄 | https://www.youtube.com/playlist?list=PLi0QOhIwpoFrSww8WHXkaUe3TzdymZ69w |
| velog suk13574 | 2025-01-11 | 개편 직전 16문항 목록, 풀이 없음 | https://velog.io/@suk13574/CAK-%EC%9E%90%EA%B2%A9%EC%A6%9D-%EC%B7%A8%EB%93%9D-%ED%9B%84%EA%B8%B0-2025%EB%85%84-1%EC%9B%94 |
| ziyad-tarek1 (26★) | 2024-12 | 38문항과 풀이, 구 유형(Gateway, Helm 없음) | https://github.com/ziyad-tarek1/CKA-Exam-Practice-Questions |
| velog kjyggg | 2023-12 | 3문항 풀이, 구 유형 | https://velog.io/@kjyggg/%EC%BF%A0%EB%B2%84%EB%84%A4%ED%8B%B0%EC%8A%A4-CKA-%EC%8B%9C%ED%97%98-%EB%B3%B5%EA%B8%B0202312 |
| velog "CKA 30제" | 2023-09 | 따배씨 영상 기반 풀이, 구 유형 | https://velog.io/@jydecn4869/CKA-30%EC%A0%9C-01-ETCD-Backup-Restore |
| taronko 티스토리 | 2023-05 | 17문항 목록, 구 유형 | https://taronko.tistory.com/17 |
| TTABAE-LEARN "CKA 기출문제 핵심 요약" | - | 한국어 구 유형, 2025 합격 후기에서 비추천 | https://www.youtube.com/playlist?list=PLApuRlvrZKog_FwzGY0OZrMMyHcgHqYTL |
| devopshubproject/cka-lab (161★) | 2022 | 25 task, 구 유형 | https://github.com/devopshubproject/cka-lab |

validexamdumps, 7sage "CKA Dumps", CliffsNotes PDF, Udemy의 "Real Exam Questions" 유료 강의는 홍보 성격이고 내용을 확인할 수 없어 목록에서 뺐습니다.
