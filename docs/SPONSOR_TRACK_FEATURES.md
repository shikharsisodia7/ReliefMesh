# Public benefit and public web features

ReliefMesh has three product paths for these Cal Hacks tracks: live public supplier-site review with Bright Data, a Claude-written explanation of a recovery plan, and an item-level view of aid exposed to a shortfall or late quoted arrival.

## Bright Data: supplier public-page review

The buyer can retrieve an Apify lead's public HTTPS website with Bright Data Web Unlocker. ReliefMesh stores the retrieval time, source URL, page title, description, and a short text excerpt beside the lead. The coordinator reviews the excerpt and source before inviting the lead. When Bright Data is configured, the lead-to-RFQ path requires a live snapshot first.

The snapshot is public web context only. It does not establish supplier eligibility, available stock, delivery capacity, or willingness to sell. Those still come from the existing screening and supplier-submitted quote workflow. ReliefMesh sends only the lead's public website URL; it does not access logins, paywalls, or non-public personal data.

Configure these backend secrets:

```dotenv
RELIEFMESH_BRIGHT_DATA_API_KEY=...
RELIEFMESH_BRIGHT_DATA_ZONE=...
```

Bright Data's [Web Unlocker API](https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website) requires an API key and an active Web Unlocker zone. The API key is not present in the local backend environment; a live retrieval still needs credentials and an actual public supplier page.

## Claude: recovery explanation

The coordinator can request a short explanation from Claude for the current plan. The prompt contains only mission requirements, deadline, item-level planned coverage, plan status/cost, and recorded change reasons. It does not include supplier emails or individual recipient details. Claude cannot change policy, calculate a plan, or approve spending. Each draft must cite source IDs, and the UI links those citations to the mission, plan comparison, or item-coverage records. The explanation is not treated as approved or shared automatically.

Configure:

```dotenv
RELIEFMESH_ANTHROPIC_API_KEY=...
RELIEFMESH_ANTHROPIC_MODEL=claude-haiku-5-5
```

The mission form optionally records a named community served. Coordinators should enter a real, substantiated community; the label is not verified by ReliefMesh. Track eligibility also depends on the team being able to explain the real problem and how it learned about it.

## People-First: aid at risk

The recovery brief compares requested quantities with the current plan's quoted arrival dates. It shows uncovered or late units by item, and marks exposure unknown while a replan is pending. These are planned quantities, not delivered supplies or a count of people served. ReliefMesh does not collect individual recipient names or personal details for this feature.

## Demo notes

Use real supplier listings and live Bright Data retrievals when presenting the public-web workflow. If either provider is not configured or the target page returns no usable result, the feature reports that state; it does not substitute a fixture. Configure provider secrets in the backend deployment before the demo. See the [Bright Data API reference](https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website) and [Anthropic Messages API](https://docs.anthropic.com/en/api/messages).
