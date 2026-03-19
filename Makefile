# ============================================
# VPN Bot - Version Management
# ============================================

# Сохранить текущее как новую версию
# Usage: make save VERSION=1.2.0 MESSAGE="описание"
save:
	@cd /root/.openclaw/workspace/vpn-bot && bash scripts/versions/save.sh $(VERSION) "$(MESSAGE)"

# Загрузить конкретную версию
# Usage: make load VERSION=golden
load:
	@cd /root/.openclaw/workspace/vpn-bot && bash scripts/versions/load.sh $(VERSION)

# Список всех версий
versions:
	@cd /root/.openclaw/workspace/vpn-bot && bash scripts/versions/list.sh

# Откатиться к golden (золотая версия)
rollback:
	@cd /root/.openclaw/workspace/vpn-bot && bash scripts/versions/load.sh golden

# Откатиться к v1.0.0
rollback-v1:
	@cd /root/.openclaw/workspace/vpn-bot && bash scripts/versions/load.sh v1.0.0
