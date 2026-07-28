# **노코드 자동매매 전략 빌더 서비스 기획 및 제안서**

---

## **Ⅰ. 사업 개요**

![logic_sample.png][image1]본 프로젝트는 금융클라우드 기반의 금융서비스 구현 역량과 생성형 AI 활용 가능성을 결합하여, 개인투자자가 보다 쉽게 자동매매 전략을 설계·검증·실행할 수 있는 서비스를 제안한다.

제안 서비스는 **AI 가이드 기반 노코드 자동 매매 전략 빌더**이다. 사용자는 별도의 프로그래밍 지식 없이도 데이터, 기술 지표, AI 분석, 조건 분기, 리스크 관리, 주문 실행 노드를 시각적으로 조합하여 주식 자동매매 전략을 구성할 수 있다.

구성된 전략은 백테스트를 통해 사전에 성과를 검증할 수 있으며, 검증이 완료된 전략은 증권사계좌와 연동하여 자동매매 형태로 실행할 수 있다. 이를 통해 개인투자자는 복잡한 자동 매매 전략 개발 과정을 보다 직관적이고 안전하게 수행할 수 있다.

본 서비스는 단순한 자동매매 도구가 아니라, 투자 전략의 설계, 검증, 실행, 관리 전 과정을 하나의 흐름으로 제공하는 **개인투자자 대상 전략 자동화 플랫폼**을 지향한다.

---

## **Ⅱ. 기획 배경**

### **1\. 시장 및 사용자 환경 변화**

최근 개인투자자의 투자 방식은 단순 매수·매도 중심에서 데이터 기반 의사결정 방식으로 점차 전환되고 있다. 기술적 지표, 재무 데이터, 뉴스, 공시, 시장 이벤트 등을 활용하여 투자 판단을 고도화하려는 수요가 증가하고 있으며, 퀀트 투자와 자동매매에 대한 관심도 지속적으로 확대되고 있다.

그러나 개인투자자가 실제로 퀀트 전략을 구현하기 위해서는 여전히 여러 제약이 존재한다. 대표적으로 프로그래밍 역량, 데이터 수집 및 정제 능력, 백테스트 환경 구축, 주문 API 연동, 리스크 관리 체계 등이 필요하다. 이러한 요소는 일반 개인투자자에게 높은 진입장벽으로 작용하고 있다.

특히 국내 주식시장 환경에서는 해외 기반 자동매매 도구를 그대로 활용하기 어렵다. 국내 시세, 공시, 뉴스, 증권사 API, 거래 제도, 투자자 보호 요건 등이 해외 시장과 다르기 때문이다. 이에 따라 국내 금융시장에 적합한 전략 설계 및 실행 도구에 대한 필요성이 존재한다.

### **2\. 기존 서비스의 한계**

현재 시장에는 자동매매 또는 전략 설계와 관련된 서비스가 일부 존재하나, 다음과 같은 한계가 있다.

첫째, 전문 개발자 또는 고급 투자자를 주요 대상으로 하는 경우가 많아 일반 개인투자자가 접근하기 어렵다. 전략을 구현하기 위해 코드 작성이 필요하거나, 복잡한 수식 및 API 사용법을 이해해야 하는 경우가 많다.

둘째, 전략의 설계와 검증, 실행이 분리되어 있다. 사용자는 별도의 데이터 분석 도구, 백테스트 도구, 주문 실행 환경을 각각 구성해야 하며, 이 과정에서 전략의 일관성과 재현성이 저하될 수 있다.

셋째, 생성형 AI의 활용이 제한적이다. 기존 서비스는 사용자가 직접 전략 조건을 정의하는 방식에 머무르는 경우가 많으며, AI가 사용자의 투자 의도를 해석하고 전략 초안을 제안하거나 노드 구성을 보조하는 기능은 충분히 제공되지 않는다.

넷째, 국내 금융 데이터와의 연계성이 제한적이라는 한계가 있다. 국내 금융시장에 적합한 시세, 공시, 뉴스, 종목 정보 등을 안정적으로 활용하기 위해서는 신뢰도 높은 데이터 공급 기반을 구축할 필요가 있다. 특히 시장 상황을 정확히 해석하기 위해서는 단순한 가격 데이터만으로는 충분하지 않다. 예를 들어 상승장에서도 부정적인 뉘앙스의 뉴스가 등장할 수 있으며, 반대로 하락장에서도 반등 가능성을 시사하는 뉴스가 발표될 수 있다. 따라서 시장 방향성을 보다 정교하게 판단하기 위해서는 시세 데이터와 뉴스 데이터를 함께 분석하는 체계가 필요하다. 이를 통해 가격 변동의 원인과 시장 심리를 종합적으로 파악하고, 국내 시장 특성을 반영한 분석 정확도를 높일 수 있다.

### **3\. 유사 서비스 비교**

| 구분 | 기존 자동매매 서비스 | 일반 노코드 자동화 도구 | 제안 서비스 |
| :---- | :---- | :---- | :---- |
| 주요 목적 | 주문 자동화 | 업무 흐름 자동화 | 투자 전략 설계·검증·실행 |
| 사용자 대상 | 고급 투자자, 개발자 | 일반 업무 사용자 | 개인투자자 및 초급 퀀트 사용자 |
| 코드 필요 여부 | 일부 필요 | 불필요 | 불필요 |
| 투자 데이터 활용 | 제한적 또는 개별 연동 | 금융 특화 아님 | 시세·공시·뉴스·지표 데이터 활용 |
| AI 활용 | 제한적 | 일반 자동화 중심 | 전략 초안 생성, 분석 보조, 판단 지원 |
| 백테스트 | 일부 제공 | 미제공 | 핵심 기능으로 제공 |
| 국내 시장 적합성 | 서비스별 상이 | 낮음 | 국내 주식시장 중심 설계 |

본 서비스는 기존 자동매매 서비스의 전문성과 노코드 도구의 접근성을 결합하고, 여기에 생성형 AI 기반 전략 설계 보조 기능을 추가한다는 점에서 차별성을 가진다.

---

## **Ⅲ. 서비스 소개**

### **1\. 서비스 개념**

본 서비스는 사용자가 노드를 조합하여 주식 자동매매 전략을 설계할 수 있는 시각적 전략 빌더이다. 전략은 여러 개의 노드가 선으로 연결된 하나의 워크플로 형태로 구성된다.

사용자는 데이터 수집, 지표 계산, AI 분석, 조건 판단, 리스크 관리, 주문 실행 과정을 각각의 노드로 구성할 수 있다. 각 노드는 하나의 기능 단위를 담당하며, 사용자는 노드를 배치하고 연결하는 방식으로 전략의 흐름을 정의한다.

이를 통해 사용자는 장 시작 전 거래대금 상위 종목 조회, 기술적 지표 및 뉴스 감성 점수 반영, 매수 후보 선별, 손절 기준 및 포지션 한도 적용, 주문 실행에 이르는 일련의 투자 전략을 코드 작성 없이 구성할 수 있다.

### **2\. 전략 워크플로 구조**

본 서비스의 핵심은 투자 전략을 하나의 흐름으로 표현하는 워크플로 구조에 있다. 워크플로는 전략 실행 조건부터 데이터 수집, 분석, 판단, 주문 실행에 이르는 절차를 구성한다.

첫 노드는 스케쥴러 노드로 고정하여 사용자가 원하는 주기마다 워크플로를 실행한다. 1초 단위 스케쥴러를 제공하여 지수 변화에 대응하도록 한다.

노드 간에는 단순한 수치나 조건값만 전달되는 것이 아니라, 종목 목록과 각 종목에 연계된 데이터가 함께 전달된다. 각 종목은 여러 노드를 통과하는 과정에서 기술 지표, 뉴스 점수, 공시 이벤트, 리스크 점수 등의 정보를 누적하게 된다.

이를 통해 사용자는 각 종목이 어떠한 판단 과정을 거쳐 매수 또는 매도 대상으로 선정되었는지 확인할 수 있다. 해당 구조는 전략의 투명성과 설명 가능성을 높이고, 사용자가 전략을 체계적으로 점검·개선할 수 있도록 지원한다.

### **3\. 핵심 기능**

#### **가. AI 기반 전략 초안 생성**

사용자는 자연어로 투자 아이디어를 입력할 수 있다. 예를 들어 “최근 뉴스가 긍정적이고 거래량이 증가한 종목 중 단기 상승 가능성이 높은 종목을 매수하고 싶다”와 같이 입력하면, AI가 이를 해석하여 기본 전략 워크플로 초안을 제안한다.

AI는 사용자의 의도를 바탕으로 필요한 데이터 노드, 지표 노드, 조건 분기 노드, 리스크 관리 노드, 주문 노드를 추천한다. 사용자는 생성된 초안을 그대로 사용하거나, 직접 수정하여 전략을 보완할 수 있다.

이 기능은 초보 사용자의 진입장벽을 낮추고, 숙련 사용자의 전략 설계 시간을 단축하는 역할을 한다.

#### **나. 노드 기반 전략 설계**

사용자는 화면에서 노드를 선택하고 연결하여 전략을 구성한다. 각 노드는 명확한 역할을 가지며, 사용자는 복잡한 코드 대신 시각적 흐름을 통해 전략을 설계한다.

| 구분 | 예시 노드 | 주요 역할 |
| :---- | :---- | :---- |
| 스케줄러 노드 | 1초 마다(유료), 1분 마다(무료) | 유료 사용자를 위한 조건 확인 주기 설정 및 시세 데이터가 변경될 때 실행 |
| 데이터 노드 | 가격, 거래량, 재무, 뉴스, 공시 | 원천 데이터 수집 |
| 지표·연산 노드 | 이동평균, RSI, 변동성, 커스텀 수식 | 매매 신호 계산 |
| AI 해석 노드 | Sentiment score(NER 기반 종목 판단), Regime | 비정형 데이터 해석 및 판단 보조 |
| 로직·제어 노드 | IF/ELSE, 필터, 랭킹, 스위치 | 조건 분기 및 흐름 제어 |
| 실행 노드 | 시장가 주문, 지정가 주문, 매도 | 계좌 연동 및 주문 실행 |

이와 같은 노드 체계를 통해 사용자는 단순한 조건식 기반 전략부터 AI 분석을 포함한 복합 전략까지 단계적으로 확장할 수 있다.

#### **다. 백테스팅**

사용자는 구성한 전략을 실제 투자에 적용하기 전에 과거 데이터를 기반으로 성과를 검증할 수 있다. 백테스트 기능은 전략의 수익률뿐 아니라 변동성, 최대 낙폭, 승률, 거래 횟수, 손익비 등 주요 성과 및 위험 지표를 제공한다.

이를 통해 사용자는 해당 전략이 특정 시장 환경에만 적합한지, 시장 변동성에 취약한지, 과도한 거래를 유발하는지 등을 사전에 검토할 수 있다.

또한 백테스트 결과를 바탕으로 전략 조건을 수정하고 재검증하는 반복 과정을 지원한다. 이는 투자 전략의 신뢰성과 실효성을 높이는 데 중요한 역할을 한다.

#### **라. 계좌 연동 및 자동매매 실행**

백테스트를 통해 검증된 전략은 증권사 계좌와 연동하여 자동매매로 실행할 수 있다. 사용자는 전략별 투자 금액, 최대 손실 한도, 종목당 투자 비중, 주문 방식 등을 설정할 수 있다.

자동매매 실행 시에는 사전에 설정한 리스크 관리 조건을 우선 적용한다. 이를 통해 전략 오류, 과도한 주문, 비정상적 시장 상황으로 인한 손실 가능성을 줄일 수 있다.

서비스는 사용자에게 전략 실행 현황, 주문 내역, 보유 종목, 손익 현황, 리스크 경고 등을 제공하여 자동매매 상태를 지속적으로 확인할 수 있도록 한다.

### **4\. 서비스 차별성**

본 서비스의 차별성은 다음과 같다.

첫째, 노코드 기반으로 전략 설계의 접근성을 높인다. 사용자는 프로그래밍 없이 전략을 설계할 수 있으며, 전략 흐름을 시각적으로 확인할 수 있다.

둘째, AI가 전략 설계 과정에 직접 관여한다. 사용자의 자연어 입력을 바탕으로 전략 초안을 생성하고, 비정형 데이터 분석과 판단 보조 기능을 제공한다.

셋째, 전략 설계, 검증, 실행을 하나의 플랫폼에서 제공한다. 사용자는 별도 도구를 조합하지 않고도 투자 전략의 전체 생애주기를 관리할 수 있다.

넷째, 국내 금융 데이터 기반 서비스로 확장 가능하다. KOSCOM의 시세, 공시, 뉴스 등 금융 데이터와 연계할 경우 데이터 신뢰도와 서비스 완성도를 높일 수 있다.

---

## **Ⅳ. 수익 모델 및 기대 효과**

### **1\. 수익 모델**

본 서비스는 단계별 기능 제공과 데이터·AI 사용량을 기준으로 수익 모델을 구성할 수 있다.

#### **가. 구독형 요금제**

기본 수익 모델은 구독제이다. 사용자는 제공 기능과 사용량에 따라 요금제를 선택한다.

| 구분 | 주요 대상 | 제공 기능 |
| :---- | :---- | :---- |
| Basic | 입문 투자자 | 기본 노드, 스케쥴러 1분 단위 설정, 제한된 백테스트, 소수 전략 저장 |
| Pro | 적극 투자자 | 고급 지표, AI 초안 생성, 스케쥴러 1초 단위 설정, 백테스트 확대, 라이브 전략 운영 |

요금제는 백테스트 횟수, AI 호출량, 사용 가능한 노드 수, 동시 실행 가능한 라이브 전략 수, 데이터 접근 범위 등을 기준으로 차등화할 수 있다.

#### **나. 마켓플레이스 수수료**

사용자가 직접 제작한 전략, 커스텀 노드, 전략 템플릿을 거래할 수 있는 마켓플레이스를 운영할 수 있다. 플랫폼은 검증된 전략 또는 노드 거래에 대해 중개 수수료를 수취한다.

다만 금융투자상품 추천 또는 투자자문에 해당하지 않도록, 전략 성과 표시 기준, 위험 고지, 검증 절차, 책임 범위를 명확히 관리해야 한다.

#### **다. 스케쥴러 세분화 및 AI 기능**

1초 단위 스케쥴링 설정 가능 기능 및 AI 초안 생성 가능 권한을 별도 과금 요소로 구성할 수 있다. 예를 들어 백테스트 횟수 추가, 실시간 뉴스 분석, 공시 이벤트 분류, 고급 시장 국면 판단, 파라미터 최적화 기능 등을 프리미엄 기능으로 제공할 수 있다.

#### **라. B2B 확장 모델**

개인투자자 대상 서비스 외에도 증권사, 투자 교육 기관, 핀테크 기업을 대상으로 한 B2B 모델로 확장할 수 있다. 예를 들어 증권사 고객용 전략 빌더, 투자 교육용 시뮬레이션 도구, 금융 데이터 활용 실습 플랫폼 등으로 제공할 수 있다.

### **2\. 기대 효과**

#### **가. 개인투자자 접근성 확대**

본 서비스는 자동매매와 퀀트 전략에 대한 진입장벽을 낮춘다. 사용자는 코드 작성 없이 전략을 구성하고, AI의 도움을 받아 투자 아이디어를 실제 실행 가능한 구조로 전환할 수 있다.

#### **나. 투자 전략 검증 문화 확산**

백테스트 기능을 통해 사용자는 감정적 투자나 단기적 판단에 의존하기보다, 데이터를 기반으로 전략을 검증할 수 있다. 이는 개인투자자의 투자 의사결정 품질을 높이는 데 기여할 수 있다.

#### **다. KOSCOM 데이터 활용 가치 확대**

KOSCOM이 보유하거나 연계 가능한 시세, 공시, 뉴스, 종목 데이터는 본 서비스의 핵심 기반 데이터로 활용될 수 있다. 신뢰도 높은 금융 데이터를 전략 설계 및 검증 과정에 제공함으로써, 데이터 활용 가치를 높일 수 있다.

#### **라. 금융클라우드 기반 서비스 구현 사례 확보**

본 프로젝트는 금융클라우드 환경에서 데이터 처리, AI 분석, 백테스트, 주문 연동 등을 구현하는 사례가 될 수 있다. 이는 향후 금융기관 및 핀테크 기업 대상 클라우드 기반 서비스 확장 가능성을 검토하는 데 활용될 수 있다.

#### **마. 생성형 AI 활용 사례 구체화**

본 서비스는 생성형 AI를 단순 질의응답 도구가 아니라 금융 전략 설계 보조 도구로 활용한다. 자연어 기반 전략 초안 생성, 뉴스 감성 분석, 시장 국면 판단, 전략 파라미터 제안 등을 통해 금융서비스 내 AI 활용 가능성을 구체적으로 제시할 수 있다.

---

## **Ⅴ. 사용자 시나리오 및 화면 설계**

### **1\. 사용자 시나리오**

본 서비스의 기본 사용자 흐름은 다음과 같다.

#### **단계 1\. 투자 아이디어 입력**

사용자는 자연어로 투자 아이디어를 입력한다.

#### **단계 2\. AI 전략 초안 생성**

AI는 사용자의 입력 내용을 분석하여 필요한 전략 구성 요소를 도출한다. 이후 스케쥴러 노드, 데이터 노드, 지표 노드, AI 해석 노드, 조건 분기 노드, 주문 노드로 구성된 기본 워크플로를 생성한다.

#### **단계 3\. 워크플로 수정**

사용자는 생성된 전략 초안을 검토하고 세부 조건을 수정한다. 주요 수정 항목에는 RSI 등 기술 지표 조건 추가, 손절 기준 조정, 매수 대상 종목 수 제한 등이 포함된다.

#### **단계 4\. 백테스트 실행**

사용자는 과거 데이터를 기반으로 전략을 검증한다. 서비스는 수익률, 최대 낙폭, 승률, 거래 횟수, 리스크 지표 등 주요 검증 결과를 제공한다.

#### **단계 5\. 전략 보완**

사용자는 백테스트 결과를 확인하고 전략 조건을 조정한다. 필요한 경우 AI 기반 개선 제안을 활용하여 전략의 조건과 구조를 보완할 수 있다.

#### **단계 6\. 계좌 연동 및 자동매매 실행**

검증이 완료된 전략은 증권사 계좌와 연동하여 자동매매로 실행할 수 있다. 사용자는 투자 금액, 주문 방식, 리스크 한도 등을 설정한 뒤 전략을 활성화한다.

#### **단계 7\. 실행 현황 모니터링**

사용자는 대시보드를 통해 전략 실행 현황, 주문 내역, 보유 종목, 손익 현황, 리스크 경고 등을 확인한다.

### **2\. 주요 화면 설계**

#### **가. 메인 대시보드**

메인 대시보드는 사용자가 운영 중인 전략을 한눈에 확인할 수 있는 화면이다.

주요 구성 요소는 다음과 같다.

| 영역 | 주요 내용 |
| :---- | :---- |
| 전략 현황 | 실행 중, 중지, 테스트 중 전략 수 |
| 성과 요약 | 전체 수익률, 당일 손익, 누적 손익 |
| 리스크 현황 | 손실 한도 접근 여부, 비정상 주문 감지 |
| 알림 | 전략 오류, 주문 실패, 시장 이벤트 |
| 빠른 실행 | 새 전략 만들기, 백테스트 실행, 계좌 연동 |

#### **나. AI 전략 생성 화면**

사용자가 자연어로 투자 아이디어를 입력하는 화면이다.

주요 기능은 다음과 같다.

| 항목 | 내용 |
| :---- | :---- |
| 자연어 입력창 | 투자 아이디어 입력 |
| AI 추천 결과 | 전략 목적, 사용 데이터, 주요 조건 제안 |
| 전략 생성 버튼 | 워크플로 초안 자동 생성 |
| 위험 고지 | AI 생성 전략은 투자 판단 보조용임을 안내 |

#### **다. 노드 기반 전략 빌더 화면**

서비스의 핵심 화면으로, 사용자가 노드를 배치하고 연결하여 전략을 구성한다.

주요 구성은 다음과 같다.

| 영역 | 주요 내용 |
| :---- | :---- |
| 노드 목록 패널 | 스케쥴러, 데이터, 지표, AI, 로직, 리스크, 실행 노드 |
| 캔버스 영역 | 전략 워크플로 구성 |
| 속성 설정 패널 | 선택한 노드의 조건 및 파라미터 설정 |
| 검증 패널 | 연결 오류, 누락 조건, 주문 위험 요소 확인 |
| 저장 및 테스트 | 전략 저장, 백테스트 실행 |

#### **라. 백테스트 결과 화면**

구성한 전략의 과거 성과를 확인하는 화면이다.

주요 구성은 다음과 같다.

| 영역 | 주요 내용 |
| :---- | :---- |
| 성과 요약 | 누적 수익률, 연환산 수익률, 벤치마크 비교 |
| 리스크 지표 | 최대 낙폭, 변동성, 손익비 |
| 거래 내역 | 매수·매도 시점, 체결 가격, 손익 |
| 차트 | 자산 곡선, 종목별 기여도, 기간별 손익 |
| 개선 제안 | AI 기반 조건 조정 제안 |

#### **마. 자동매매 실행 및 모니터링 화면**

실제 계좌와 연동된 전략의 실행 상태를 관리하는 화면이다.

주요 구성은 다음과 같다.

| 영역 | 주요 내용 |
| :---- | :---- |
| 실행 상태 | 전략 활성화 여부, 최근 실행 시각 |
| 계좌 정보 | 연동 계좌, 사용 가능 금액, 보유 종목 |
| 주문 내역 | 주문 요청, 체결, 실패 내역 |
| 긴급 제어 | 전략 일시정지, 전체 주문 중단 |

---

## **Ⅵ. 아키텍처**

### **1\. 아키텍처 설계 방향**

본 서비스의 아키텍처는 안정성, 확장성, 보안성, 검증 가능성을 중심으로 설계한다. 특히 금융서비스 특성상 사용자 계좌 연동, 주문 실행, 투자 데이터 처리 과정에서 높은 신뢰성이 요구된다.

따라서 전략 설계 영역, 데이터 처리 영역, AI 분석 영역, 백테스트 영역, 주문 실행 영역을 분리하여 구성한다. 각 영역은 독립적으로 확장 가능해야 하며, 장애 발생 시 전체 서비스로 영향이 확산되지 않도록 설계한다.

### **2\. 주요 구성 요소**

| 구성 요소 |  | 주요 역할 |
| :---- | :---- | :---- |
| 사용자 인터페이스 |  | 전략 생성, 노드 편집, 백테스트 결과 확인, 자동매매 관리 |
| API 서버 |  | 사용자 요청 처리, 인증·인가, 전략 저장 및 실행 요청 관리 |
| 전략 워크플로 엔진 |  | 노드 연결 구조 해석, 전략 실행 순서 관리 |
| 데이터 수집 모듈 |  | 시세, 재무, 뉴스, 공시 등 원천 데이터 수집 |
| AI 분석 모듈 |  | 자연어 전략 해석, 뉴스 감성 분석, 시장 국면 판단 |
| 백테스트 엔진 |  | 과거 데이터 기반 전략 성과 검증 |
| 주문 실행 모듈 |  | 증권사 API 연동, 주문 요청 및 체결 결과 관리 |
| 데이터베이스 |  | 사용자, 전략, 백테스트 결과, 주문 이력 저장 |
| 모니터링 시스템 |  | 장애, 주문 실패, 성능 지표, 이상 거래 감지 |

### **3\. 서비스 처리 흐름**

서비스의 기본 처리 흐름은 다음과 같다.

1\.     사용자가 자연어로 전략 아이디어를 입력한다.

2\.     AI 분석 모듈이 전략 의도를 해석하고 워크플로 초안을 생성한다.

3\.     사용자는 노드 기반 전략 빌더에서 전략을 수정한다.

4\.     저장된 전략은 워크플로 엔진을 통해 실행 가능한 형태로 변환된다.

5\.     백테스트 엔진은 과거 데이터를 활용하여 전략 성과를 검증한다.

6\.     사용자는 백테스트 결과를 확인하고 전략을 보완한다.

7\.     계좌 연동 후 자동매매 실행을 승인한다.

8\.     주문 실행 모듈은 증권사 API와 연동하여 주문을 수행한다.

9\.     리스크 관리 모듈은 사전에 설정한 제한 조건을 지속적으로 점검한다.

10\. 모니터링 시스템은 전략 실행 상태와 이상 상황을 사용자에게 제공한다.

### **4\. 보안 및 안정성 고려사항**

금융서비스 특성상 다음 사항을 필수적으로 고려해야 한다.

첫째, 사용자 인증 및 권한 관리를 강화해야 한다. 계좌 연동, 주문 실행, 전략 활성화와 같은 주요 기능은 별도의 인증 절차를 적용할 필요가 있다.

둘째, 주문 실행 전 리스크 검증 절차를 두어야 한다. 비정상 주문, 과도한 주문 수량, 손실 한도 초과, 계좌 잔고 부족 등의 상황을 사전에 차단해야 한다.

셋째, 모든 전략 실행 및 주문 이력은 추적 가능해야 한다. 사용자가 어떤 전략 조건에 따라 어떤 주문이 발생했는지 확인할 수 있어야 하며, 장애 또는 분쟁 발생 시 원인 분석이 가능해야 한다.

넷째, AI 판단 결과는 투자 판단의 보조 정보로 제한해야 한다. AI가 생성한 전략 또는 분석 결과에 대해서는 충분한 고지와 검증 절차를 제공해야 하며, 최종 실행 권한은 사용자에게 있어야 한다.

다섯째, 금융 데이터의 정확성과 최신성을 관리해야 한다. 시세, 공시, 뉴스 등 주요 데이터는 출처와 갱신 시점을 명확히 관리해야 하며, 데이터 오류 발생 시 전략 실행에 미치는 영향을 최소화해야 한다.

### **5\. 기대 아키텍처 효과**

본 아키텍처는 전략 설계, 검증, 실행을 각각 독립된 구성 요소로 분리함으로써 기능 확장과 장애 대응에 유리하다. 또한 금융클라우드 기반으로 구성할 경우 데이터 보안, 서비스 운영 안정성, 확장성을 확보할 수 있다.

특히 KOSCOM의 금융 데이터와 연계할 경우, 신뢰도 높은 데이터 기반의 전략 설계 및 백테스트 환경을 제공할 수 있다. 이는 일반 자동매매 서비스와 차별화되는 핵심 기반이 될 수 있다.

[image1]: <data:image/png;base64,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>