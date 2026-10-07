# =============================================================================
#  _common.sh : 모든 실행 스크립트 공통 (직접 실행하지 않음, source 전용)
#   - env.sh 확인 후 불러오기
#   - 포트 설정이 예시값(XXXXXXXX 등) 그대로이거나 장치가 없으면 즉시 알림
#   - 같은 프로그램 중복 실행 방지 (한 포트를 두 프로세스가 읽으면 데이터가 나뉘어 누락됨)
# =============================================================================
SF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_die()  { echo -e "\033[1;31m✘ $*\033[0m" >&2; exit 1; }
_warn() { echo -e "\033[1;33m⚠ $*\033[0m" >&2; }

sf_load_env() {
    [ -f "$SF_ROOT/scripts/env.sh" ] || _die "scripts/env.sh 가 없습니다 → cp $SF_ROOT/scripts/env.sh.example $SF_ROOT/scripts/env.sh 후 포트를 수정하세요"
    # shellcheck disable=SC1091
    source "$SF_ROOT/scripts/env.sh"
    [ -n "${SF_DB_PATH:-}" ] || _die "env.sh 에 SF_DB_PATH 가 없습니다"
    [ -n "${SF_HUB_SOCK:-}" ] || _die "env.sh 에 SF_HUB_SOCK 이 없습니다"
}

# sf_check_port 변수이름 설명  → 예시값/미존재/권한 문제를 시작 전에 알림
sf_check_port() {
    local var="$1" what="$2" path="${!1:-}"
    [ -n "$path" ] || _die "$var 가 비어 있습니다 ($what)"
    case "$path" in *XXXXXXXX*|*YYYYYYYY*|*ZZZZZZZZ*)
        _die "$var 가 예시값입니다 ($what). ls -l /dev/serial/by-id/ 로 확인해 env.sh 를 수정하세요" ;;
    esac
    if [ ! -e "$path" ]; then
        _warn "$what 포트가 없습니다: $path  (usbipd attach 확인). 연결될 때까지 재시도합니다"
    elif [ ! -r "$path" ] || [ ! -w "$path" ]; then
        _die "$what 포트 권한 없음: $path → sudo usermod -aG dialout \$USER 후 재로그인 (임시: sudo chmod a+rw /dev/ttyACM*)"
    fi
}

# sf_single_instance 이름 → 같은 이름으로 이미 실행 중이면 중단 (프로세스가 끝나면 자동 해제)
sf_single_instance() {
    local lock="/tmp/sf_${1}.lock"
    exec 9>"$lock" || _die "잠금 파일을 만들 수 없습니다: $lock"
    flock -n 9 || _die "$1 이(가) 이미 실행 중입니다. 다른 터미널을 확인하세요 (중복 실행 시 데이터 누락·포트 충돌)"
}
