/* Jinja2 snippet catalog for the Template tab.
   $|$ marks the cursor-rest position after insertion. */
window.JINJA_SNIPPETS = [
  // ========================================================================
  // Control flow
  // ========================================================================
  { cat: 'Control flow', name: 'if',
    body: '{% if $|$ %}\n    \n{% endif %}' },
  { cat: 'Control flow', name: 'if / else',
    body: '{% if $|$ %}\n    \n{% else %}\n    \n{% endif %}' },
  { cat: 'Control flow', name: 'if / elif / else',
    body: '{% if $|$ %}\n    \n{% elif cond2 %}\n    \n{% else %}\n    \n{% endif %}' },
  { cat: 'Control flow', name: 'for loop',
    body: '{% for item in $|$ %}\n    {{ item }}\n{% endfor %}' },
  { cat: 'Control flow', name: 'for / else (empty case)',
    body: '{% for item in $|$ %}\n    {{ item }}\n{% else %}\n    ! no items\n{% endfor %}' },
  { cat: 'Control flow', name: 'for with index',
    body: '{% for item in $|$ %}\n    {{ loop.index }}: {{ item }}\n{% endfor %}' },
  { cat: 'Control flow', name: 'for with comma separator',
    body: '{{ item }}{% if not loop.last %}, {% endif %}' },
  { cat: 'Control flow', name: 'set variable',
    body: "{% set $|$ = '' %}" },
  { cat: 'Control flow', name: 'macro',
    body: '{% macro name($|$) %}\n    \n{% endmacro %}' },

  // ========================================================================
  // Variables & output
  // ========================================================================
  { cat: 'Variables', name: 'variable',
    body: '{{ $|$ }}' },
  { cat: 'Variables', name: "variable w/ default",
    body: "{{ $|$ | default('') }}" },
  { cat: 'Variables', name: "variable w/ default (strict — applies if empty)",
    body: "{{ $|$ | default('', true) }}" },
  { cat: 'Variables', name: 'attribute',
    body: '{{ $|$.attr }}' },

  // ========================================================================
  // Comments & whitespace
  // ========================================================================
  { cat: 'Comments & whitespace', name: 'comment',
    body: '{# $|$ #}' },
  { cat: 'Comments & whitespace', name: 'trim whitespace',
    body: '{%- $|$ -%}' },

  // ========================================================================
  // Loop helpers (inside {% for %})
  // ========================================================================
  { cat: 'Loop helpers', name: 'loop.index  (1-based)',
    body: '{{ loop.index }}' },
  { cat: 'Loop helpers', name: 'loop.first',
    body: '{% if loop.first %}$|${% endif %}' },
  { cat: 'Loop helpers', name: 'loop.last',
    body: '{% if loop.last %}$|${% endif %}' },

  // ========================================================================
  // Filters — text
  // ========================================================================
  { cat: 'Filters · text', name: 'lower',
    body: '| lower' },
  { cat: 'Filters · text', name: 'upper',
    body: '| upper' },
  { cat: 'Filters · text', name: 'title  (Hello World)',
    body: '| title' },
  { cat: 'Filters · text', name: 'trim',
    body: '| trim' },
  { cat: 'Filters · text', name: 'replace',
    body: "| replace('$|$', '')" },
  { cat: 'Filters · text', name: 'indent(N)',
    body: '| indent(4)' },

  // ========================================================================
  // Filters — numbers
  // ========================================================================
  { cat: 'Filters · numbers', name: 'round',
    body: '| round' },
  { cat: 'Filters · numbers', name: 'int',
    body: '| int' },
  { cat: 'Filters · numbers', name: 'float',
    body: '| float' },

  // ========================================================================
  // Filters — sequences / lists
  // ========================================================================
  { cat: 'Filters · sequences', name: 'length',
    body: '| length' },
  { cat: 'Filters · sequences', name: 'first',
    body: '| first' },
  { cat: 'Filters · sequences', name: 'last',
    body: '| last' },
  { cat: 'Filters · sequences', name: 'sort',
    body: '| sort' },
  { cat: 'Filters · sequences', name: 'sort by attribute',
    body: "| sort(attribute='$|$')" },
  { cat: 'Filters · sequences', name: 'unique',
    body: '| unique' },
  { cat: 'Filters · sequences', name: 'join',
    body: "| join(', ')" },
  { cat: 'Filters · sequences', name: 'selectattr  (keep where truthy)',
    body: "| selectattr('$|$')" },
  { cat: 'Filters · sequences', name: 'rejectattr  (drop where truthy)',
    body: "| rejectattr('$|$')" },
  { cat: 'Filters · sequences', name: 'map to attribute',
    body: "| map(attribute='$|$')" },

  // ========================================================================
  // Filters — defaults / types / escape
  // ========================================================================
  { cat: 'Filters · defaults', name: 'default',
    body: "| default('$|$')" },
  { cat: 'Filters · defaults', name: 'string',
    body: '| string' },
  { cat: 'Filters · defaults', name: 'safe  (trusted HTML)',
    body: '| safe' },
  { cat: 'Filters · defaults', name: 'tojson',
    body: '| tojson' },

  // ========================================================================
  // Tests (with `is`)
  // ========================================================================
  { cat: 'Tests', name: 'is defined',
    body: 'is defined' },
  { cat: 'Tests', name: 'is none',
    body: 'is none' },
  { cat: 'Tests', name: 'is number',
    body: 'is number' },
  { cat: 'Tests', name: 'is string',
    body: 'is string' },
  { cat: 'Tests', name: 'is even',
    body: 'is even' },

  // ========================================================================
  // IP helpers  (for fields typed ipv4_address, ipv6_address, or cidr)
  // ========================================================================
  { cat: 'IP helpers', name: 'address  (host IP, no mask)',
    body: '{{ $|$.address }}' },
  { cat: 'IP helpers', name: 'network  (network address)',
    body: '{{ $|$.network }}' },
  { cat: 'IP helpers', name: 'netmask  (dotted-decimal)',
    body: '{{ $|$.netmask }}' },
  { cat: 'IP helpers', name: 'wildcard  (inverse mask, v4)',
    body: '{{ $|$.wildcard }}' },
  { cat: 'IP helpers', name: 'broadcast  (v4 only)',
    body: '{{ $|$.broadcast }}' },
  { cat: 'IP helpers', name: 'cidr  (network/prefix)',
    body: '{{ $|$.cidr }}' },
  { cat: 'IP helpers', name: 'host_cidr  (host/prefix)',
    body: '{{ $|$.host_cidr }}' },
  { cat: 'IP helpers', name: 'prefix  (length as int)',
    body: '{{ $|$.prefix }}' },
  { cat: 'IP helpers', name: 'first  (first usable host)',
    body: '{{ $|$.first }}' },
  { cat: 'IP helpers', name: 'last  (last usable host)',
    body: '{{ $|$.last }}' },
  { cat: 'IP helpers', name: 'hosts  (usable host count)',
    body: '{{ $|$.hosts }}' },
  { cat: 'IP helpers', name: 'version  (4 or 6)',
    body: '{{ $|$.version }}' },
  { cat: 'IP helpers', name: 'is_private',
    body: '{{ $|$.is_private }}' },
  { cat: 'IP helpers', name: 'reverse_pointer  (DNS PTR name)',
    body: '{{ $|$.reverse_pointer }}' },
  { cat: 'IP helpers', name: 'exploded  (full v6 form)',
    body: '{{ $|$.exploded }}' },
  { cat: 'IP helpers', name: 'compressed  (short v6 form)',
    body: '{{ $|$.compressed }}' },

  // ========================================================================
  // Network idioms  (assume standard variable names — rename to taste)
  // ========================================================================
  { cat: 'Network idioms', name: 'Interface block',
    body:
      '{% for intf in interfaces %}\n' +
      'interface {{ intf.name }}\n' +
      ' description {{ intf.description }}\n' +
      ' ip address {{ intf.ip }} {{ intf.mask }}\n' +
      ' no shutdown\n' +
      '!\n' +
      '{% endfor %}' },
  { cat: 'Network idioms', name: 'VLAN definitions',
    body:
      '{% for vlan in vlans %}\n' +
      'vlan {{ vlan.id }}\n' +
      ' name {{ vlan.name }}\n' +
      '!\n' +
      '{% endfor %}' },
  { cat: 'Network idioms', name: 'Static routes',
    body:
      '{% for r in static_routes %}\n' +
      'ip route {{ r.prefix }} {{ r.mask }} {{ r.next_hop }}\n' +
      '{% endfor %}' },
  { cat: 'Network idioms', name: 'NTP servers',
    body:
      '{% for s in ntp_servers %}\n' +
      'ntp server {{ s }}\n' +
      '{% endfor %}' },
  { cat: 'Network idioms', name: 'DNS name-servers',
    body:
      '{% for s in dns_servers %}\n' +
      'ip name-server {{ s }}\n' +
      '{% endfor %}' },
  { cat: 'Network idioms', name: 'BGP neighbors',
    body:
      'router bgp {{ bgp_asn }}\n' +
      '{% for n in bgp_neighbors %}\n' +
      ' neighbor {{ n.ip }} remote-as {{ n.remote_asn }}\n' +
      ' neighbor {{ n.ip }} description {{ n.description }}\n' +
      '{% endfor %}' },
  { cat: 'Network idioms', name: 'ACL entries (extended)',
    body:
      'ip access-list extended {{ acl_name }}\n' +
      '{% for rule in acl_rules %}\n' +
      ' {{ rule.action }} {{ rule.protocol }} {{ rule.src }} {{ rule.dst }}\n' +
      '{% endfor %}' },
  { cat: 'Network idioms', name: 'Banner MOTD',
    body:
      'banner motd ^\n' +
      '{{ banner_message | indent(2, true) }}\n' +
      '^' },
  { cat: 'Network idioms', name: 'Conditional feature toggle',
    body:
      '{% if enable_$|$ %}\n' +
      '! feature enabled\n' +
      '{% endif %}' },
];
