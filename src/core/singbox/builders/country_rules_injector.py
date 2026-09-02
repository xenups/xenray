"""Sing-box Country rules injector."""

from __future__ import annotations

from src.core.constants import SINGBOX_RULE_SETS
from src.core.logger import logger


class CountryRulesInjector:
    """Injects country-based direct routing rule-sets into sing-box route and DNS config."""

    def inject(self, cfg_route: dict, dns_rules: list, routing_country: str) -> None:
        """Inject country-based direct routing via rule-set in-place.

        Args:
            cfg_route: Target sing-box route block dict (will have ``rule_set`` and ``rules`` modified).
            dns_rules: Target sing-box dns rules list.
            routing_country: ISO country code (e.g. 'ir', 'cn', 'ru').
        """
        if not routing_country or routing_country.lower() == "none":
            return

        country = routing_country.lower()
        rule_sets_mapping = SINGBOX_RULE_SETS

        if country not in rule_sets_mapping:
            logger.warning(f"[CountryRulesInjector] Unknown country code '{country}'")
            return

        logger.info(f"[CountryRulesInjector] Applying country routing: {country}")

        if "rule_set" not in cfg_route:
            cfg_route["rule_set"] = []

        for idx, url in enumerate(rule_sets_mapping[country]):
            tag_name = f"{country}-rules-{idx}"
            logger.debug(f"[CountryRulesInjector] Adding rule set: {tag_name} from {url}")

            from src.core.singbox.builders.rule_set_utils import materialize_rule_set

            # Offline-first: cached on disk -> local; missing -> both the rule-set
            # and its dependent rules are dropped (never a remote @url fetch FATAL).
            rule_set = materialize_rule_set(tag_name, url, download_detour="proxy")
            if rule_set is None:
                continue
            cfg_route["rule_set"].append(rule_set)
            cfg_route["rules"].append({"rule_set": tag_name, "outbound": "direct"})
            dns_rules.append({"rule_set": tag_name, "server": "bootstrap"})
            logger.info(f"[CountryRulesInjector] Country rule added: {tag_name} → direct")
