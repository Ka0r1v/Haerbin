# Topic Recall 与 Top-5000 漏检分析

qrels：`rag25-climbmix-umbrela-codex-gpt5.5-medium-reasoning-v1.qrels`；相关阈值：`>=2`；focus run：`V3`。

## 逐 topic 覆盖

| qid | 相关总数 | BM25 R@100 | BM25 R@1000 | V2 R@100 | V2 R@1000 | V2 R@5000 | V3 R@100 | V3 R@1000 | V3 R@5000 | V3 漏检@5000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 14 | 695 | 0.122 | 0.245 | 0.102 | 0.286 | 0.440 | 0.105 | 0.288 | 0.440 | 389 |
| 31 | 925 | 0.106 | 0.289 | 0.089 | 0.308 | 0.469 | 0.091 | 0.311 | 0.469 | 491 |
| 37 | 827 | 0.105 | 0.164 | 0.083 | 0.203 | 0.325 | 0.083 | 0.202 | 0.325 | 558 |
| 58 | 516 | 0.182 | 0.428 | 0.136 | 0.459 | 0.661 | 0.141 | 0.465 | 0.661 | 175 |
| 72 | 901 | 0.102 | 0.299 | 0.084 | 0.356 | 0.523 | 0.084 | 0.360 | 0.523 | 430 |
| 84 | 701 | 0.114 | 0.277 | 0.104 | 0.284 | 0.398 | 0.107 | 0.284 | 0.398 | 422 |
| 144 | 421 | 0.033 | 0.112 | 0.069 | 0.302 | 0.644 | 0.067 | 0.325 | 0.644 | 150 |
| 161 | 687 | 0.127 | 0.317 | 0.112 | 0.415 | 0.684 | 0.116 | 0.421 | 0.684 | 217 |
| 200 | 494 | 0.059 | 0.130 | 0.055 | 0.172 | 0.298 | 0.057 | 0.178 | 0.298 | 347 |
| 213 | 173 | 0.098 | 0.312 | 0.214 | 0.613 | 0.769 | 0.214 | 0.624 | 0.769 | 40 |
| 219 | 580 | 0.100 | 0.169 | 0.072 | 0.193 | 0.324 | 0.074 | 0.193 | 0.324 | 392 |
| 224 | 653 | 0.135 | 0.266 | 0.107 | 0.334 | 0.564 | 0.110 | 0.335 | 0.564 | 285 |
| 225 | 555 | 0.142 | 0.526 | 0.110 | 0.485 | 0.699 | 0.112 | 0.486 | 0.699 | 167 |
| 233 | 787 | 0.086 | 0.264 | 0.098 | 0.371 | 0.595 | 0.100 | 0.375 | 0.595 | 319 |
| 273 | 330 | 0.152 | 0.273 | 0.124 | 0.348 | 0.470 | 0.124 | 0.348 | 0.470 | 175 |
| 300 | 635 | 0.117 | 0.216 | 0.098 | 0.302 | 0.428 | 0.101 | 0.306 | 0.428 | 363 |
| 407 | 296 | 0.125 | 0.257 | 0.095 | 0.267 | 0.341 | 0.095 | 0.270 | 0.341 | 195 |
| 477 | 525 | 0.101 | 0.278 | 0.088 | 0.330 | 0.507 | 0.091 | 0.330 | 0.507 | 259 |
| 499 | 609 | 0.140 | 0.558 | 0.118 | 0.612 | 0.841 | 0.120 | 0.617 | 0.841 | 97 |
| 515 | 414 | 0.022 | 0.060 | 0.043 | 0.205 | 0.461 | 0.046 | 0.208 | 0.461 | 223 |
| 707 | 586 | 0.089 | 0.183 | 0.087 | 0.287 | 0.575 | 0.090 | 0.304 | 0.575 | 249 |
| 897 | 674 | 0.122 | 0.237 | 0.102 | 0.306 | 0.481 | 0.105 | 0.300 | 0.481 | 350 |

已知相关文档不是每题只有几十篇：最少 `173`，中位数 `609`，最多 `925`。

## 漏检样本中的查询缺口

每题从 `V3` Top-5000 之外按 qrels grade 优先抽样最多 5 篇。以下结论只代表样本，不代表该 topic 的全部漏检文档。

| qid | 实体/别名 | 时间 | 地点 | 术语 | 未覆盖 facet | 建议路由 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 14 | college football；NIL rights | prehistoric/ancient；future trends | — | Ping Pong Diplomacy；athleisure | peace & diplomacy through sports；youth sport equity and inclusion | terminology: Ping Pong Diplomacy sports peace；facet: youth sport equity inclusion narrative；terminology: athleisure sports fashion celebrity endorsement；temporal: history of archery equipment evolution | medium |
| 31 | WEEE；electronic waste | 2015；2016/2022 statistics | developing countries (export context) | toxic chemicals；landfill | other waste types beyond e-waste；practical steps for individuals/businesses | terminology: WEEE recycling environmental impact；facet: practical steps for businesses to recycle e-waste；facet: recent innovations in e-waste recycling technology；facet: health risks of e-waste for workers in developing countries | medium |
| 37 | — | — | — | child abuse；resilience | causes and consequences of child abuse；resilience building strategies | terminology: child abuse causes and effects on children；terminology: building resilience in children parenting strategies；facet: parent-child attachment development and well-being；facet: parental involvement student performance life satisfaction | medium |
| 58 | NCPA；TAE | 2008；2010 | — | baseload electricity；proliferation | security implications of expanded nuclear energy；nuclear waste recycling as sustainability | terminology: nuclear power baseload electricity emissions comparison；facet: nuclear proliferation risks expanded nuclear energy；entity_alias: NCPA report nuclear power safety；entity_alias: TAE nuclear fusion non-radioactive | medium |
| 72 | — | — | Amazon rainforest | soil erosion；food chain | detailed effects on humans (e.g., soil erosion)；specific statistics on deforestation rates | facet: deforestation effects on humans soil erosion health；terminology: deforestation statistics acres lost per year；geographic: Amazon rainforest deforestation food chain impact；facet: causes of deforestation fires urbanization mining | medium |
| 84 | Antivaxxer Movement；Henning Jacobson | 1901–1903 smallpox epidemic；Omicron variant emergence (2021) | Boston/Cambridge (US)；Pakistan/Afghanistan/Nigeria (polio) | immunizations (used interchangeably with vaccines)；acellular pertussis | pregnancy safety during vaccination；specific global epidemics (dengue, malaria, cholera) | entity_alias: antivaxxer movement 1900s smallpox resistance；temporal: 1901 smallpox epidemic Boston compulsory vaccination；geographic: vaccination rates in Nigeria Pakistan Afghanistan polio；terminology: acellular pertussis vaccine safety reactogenicity | medium |
| 144 | — | — | — | FDIC；NCUA | ownership structure differences；deposit insurance comparison (FDIC vs NCUA) | terminology: FDIC vs NCUA insurance for banks and credit unions；facet: credit union ownership member owned cooperative；facet: pros and cons of banks versus credit unions；facet: how credit unions are different from banks nonprofit | medium |
| 161 | Dobbs v. Jackson Women's Health Organization；Planned Parenthood v. Casey | quickening (pre-viability historical standard)；1973 Roe v. Wade to 2022 Dobbs reversal timeline | India (Article 21 of constitution)；Canada (dictionary definition) | Imago Dei；viability | comparative human rights frameworks (ICCPR, Indian constitution)；historical concept of quickening as benchmark | entity_alias: Dobbs v Jackson abortion history；terminology: Imago Dei Christian abortion views；geographic: abortion rights India constitution Article 21；temporal: quickening abortion historical acceptance | high |
| 200 | Shoah；Führer | January 30, 1933；1933-1945 | Hrubieszow；Eastern Front | Final Solution；Enabling Act | personal survivor testimonies；glossary of Holocaust terms | entity_alias: Shoah persecution Jews 1933；terminology: Final Solution Aktion Reinhard Holocaust；geographic: Holocaust Eastern Front Soviet Union；temporal: Hitler becomes chancellor January 30 1933 Holocaust | medium |
| 213 | Truman；MacArthur | June 1950 invasion date；1943-1945 conference period | 38th parallel；Inchon | trusteeship；amphibious assault | pre-war Allied negotiations；specific military operation (Inchon landing) | entity_alias: Truman decision Korean War；entity_alias: MacArthur Inchon landing；temporal: 1945 division of Korea 38th parallel；geographic: Inchon amphibious operation 1950 | medium |
| 219 | Artificial intelligence vs AI；Electronic Health Records vs telehealth | — | United States healthcare (doc1)；Australia mHealth (doc4) | mHealth vs telehealth；Extended Reality (XR) vs general technology impact | role of technical societies；rationing devices rationale | terminology: digital health OR electronic health records OR mHealth societal impact；terminology: AI benefits and drawbacks society healthcare；entity_alias: AI positive negative effects daily life government business；geographic: Australia mHealth cardiac rehabilitation technology | medium |
| 224 | repatriates (for returning Portuguese colonialists)；environmental refugees (for climate migrants) | historical periods (1970s, 1990s)；future projections (2023, 2050) | Portugal；Western Europe (Yugoslavia, Somalia, Sri Lanka context) | social transfers；asylum-seeker vs refugee legal distinction | anti-migration political tactics and misperceptions；refugee camp living conditions and legal limbo | terminology: anti-immigration political misperceptions far-right tactics；facet: refugee camp conditions legal status asylum-seeker；temporal: asylum applications western Europe 1990s recognition rate；facet: children immigrant families integration education poverty | high |
| 225 | First Person Shooters (FPS)；Grand Theft Auto | 1980s/1983 crash/historical industry growth；2015 publication date | United States (U.S. children statistics)；North America (industry crash) | aggression vs 'anti-social tendencies' or 'youth violence'；addiction vs 'gaming disorder' | counterarguments or null results (Oxford study)；positive aspects (problem-solving, stress relief) | entity_alias: FPS games antisocial children；temporal: history of video game industry growth 1980s；geographic: American children violent video game statistics；terminology: gaming disorder addiction video games | medium |
| 233 | Instagram；Snapchat | 2015；2017 | UK；Scotland | FOMO；#StatusOfMind | specific Royal Society for Public Health study；comparison of multiple platforms' mental health impact | entity_alias: Instagram worst social media mental health teenagers；terminology: #StatusOfMind survey teens depression anxiety；geographic: Royal Society for Public Health social media mental health；facet: social media depression body image sleep teens | high |
| 273 | — | 2012 (poorest countries list dated)；1960s (independence era) | Namibia; ACCRA, DAKAR, JOHANNESBURG (specific places not in query)；sub-Saharan Africa (rather than broad 'Africa') | green hydrogen (specific technology)；SAPs (structural adjustment programs) | post-colonial governance failures and mismanagement；energy poverty and infrastructure challenges | temporal: Africa underdevelopment post-independence 1960s；geographic: sub-Saharan Africa energy poverty consumption；terminology: structural adjustment programs Africa economic reform；terminology: SDGs sub-Saharan Africa progress poverty | medium |
| 300 | — | — | California；Bangladesh | mitigation vs. prevention；greenhouse gas emissions vs. global warming | specific state-level policy (AB32)；international panel synthesis | terminology: climate change mitigation strategies；geographic: California AB32 climate action；terminology: IPCC mitigation options report；facet: WWF stop climate change 15 ways | high |
| 407 | Dubai not mentioned; relevant docs discuss Canada, Australia, US | — | Dubai vs Canada, Australia, US | planning restrictions；zoning laws | role of immigration in housing demand；gentrification and displacement | terminology: zoning laws housing affordability；terminology: planning restrictions house prices；terminology: gentrification displacement housing；geographic: Canada housing expensive reasons | high |
| 477 | — | — | — | biogenetically distinct races；dog breed analogy | Brazil perspective on race；Critical Race Theory objections | terminology: biogenetically distinct races refuted；terminology: dog breed analogy human races；terminology: clinal variation human race；terminology: descent based groupings genetics | high |
| 499 | physician-assisted suicide vs euthanasia | — | — | active euthanasia；passive euthanasia | definitions and types of euthanasia；specific arguments: religious, slippery slope, medical ethics, alternative/end-of-life care | terminology: active passive voluntary involuntary euthanasia definition；terminology: difference between euthanasia and physician assisted suicide；facet: religious arguments against euthanasia；facet: slippery slope argument euthanasia legalization | medium |
| 515 | Children with Cancer UK；millennials | — | UK | electromagnetic fields；obesity-linked cancers | breast cancer mortality UK；lung cancer life expectancy | terminology: electromagnetic fields radiation cancer children young；terminology: obesity young adult cancer risk rising；entity_alias: Children with Cancer UK young cancer increase；facet: colorectal cancer young adults rising incidence | medium |
| 707 | — | — | — | organophosphate poisoning vs pesticide exposure；dichlorvos specific chemical not in query | antiperspirants and sorbitol as specific chemical examples not covered in missed documents | terminology: organophosphate poisoning children health effects；terminology: dichlorvos insecticide health risks；facet: pesticide exposure schools children；facet: home pesticides bird toxicity | medium |
| 897 | — | — | Tennessee (document [3])；Europe/Stockholm (document [4]) | substance use disorders (vs. alcohol use)；DSM-5 (not mentioned in query) | policy and community-level prevention (documents [2], [4])；genetic and environmental interplay (document [5]) | terminology: substance use disorders DSM-5 epidemiology prevention；geographic: alcohol outlet neighborhood safety community health；facet: genetic predisposition addiction environmental factors；geographic: young people alcohol policy Europe Stockholm declaration | high |

建议路由类型频次：`facet`=48、`terminology`=43、`geographic`=16、`entity_alias`=14、`temporal`=10

## 方法限制

- qrels 是池化/LLM judgment，不是对 ClimbMix 全库的穷举人工标注。
- 漏检文本分析使用每题少量高 grade 样本，适合发现模式，不适合估计模式占比。
- V2/V3 的 dense、ColBERT 和 RankLLM 都只处理已有候选，不能恢复未进入 Top-5000 的文档。
