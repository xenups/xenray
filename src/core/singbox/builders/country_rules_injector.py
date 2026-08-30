"""Sing-box Country rules injector."""

from __future__ import annotations

from typing import List

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

            cfg_route["rule_set"].append(
                {
                    "tag": tag_name,
                    "type": "remote",
                    "format": "binary",
                    "url": url,
                    # Download through the tunneled proxy so censored networks
                    # can fetch the rules (direct githubusercontent is blocked).
                    "download_detour": "proxy",
                    "update_interval": "24h",
                }
            )
            cfg_route["rules"].append({"rule_set": tag_name, "outbound": "direct"})
            dns_rules.append({"rule_set": tag_name, "server": "bootstrap"})
            logger.info(f"[CountryRulesInjector] Country rule added: {tag_name} → direct")
