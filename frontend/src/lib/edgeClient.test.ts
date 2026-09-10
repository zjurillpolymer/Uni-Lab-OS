import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  adaptMaterial,
  adaptTask,
  adaptWorkflow,
  createExperimentOperation,
  createWorkflowTask,
  decideWorkflowIntervention,
  createReagent,
  createReagentInfo,
  deleteReagentInfo,
  EdgeApiError,
  deleteReagent,
  dispenseReagent,
  instantiateMaterial,
  lookupCompoundByCas,
  loadActionTemplates,
  loadControlTemplates,
  loadEdgeSnapshot,
  loadReagentHistory,
  loadWorkflowGraph,
  loadWorkflowTaskDetail,
  loadWorkflowTaskGraph,
  startupModeSwitchBlockers,
  switchStartupMode,
  unwrapEnvelope,
  updateExperimentOperation,
  updateReagent,
} from './edgeClient'

afterEach(() => vi.unstubAllGlobals())

function response(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

describe('unwrapEnvelope', () => {
  it('returns data for a successful Edge response', () => {
    expect(unwrapEnvelope({ code: 0, data: { items: [1, 2] } })).toEqual({ items: [1, 2] })
  })

  it('rejects an Edge business error even if HTTP succeeded', () => {
    expect(() => unwrapEnvelope({ code: 1000, error: { msg: 'invalid cursor' } })).toThrow('invalid cursor')
  })
})

describe('decideWorkflowIntervention', () => {
  it('rejects a business error returned with HTTP 200', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      code: 1000,
      error: { msg: '设备暂不可达' },
    })))

    await expect(decideWorkflowIntervention({
      uuid: 'intervention-1', workflowTaskUuid: 'task-1', workflowNodeJobUuid: 'job-1',
      revision: 1, status: 'open', options: [], metaData: {}, openedAt: '',
    }, 'retry')).rejects.toThrow('设备暂不可达')
  })
})

describe('switchStartupMode', () => {
  it('switches the runtime session using the last observed mode', async () => {
    const fetchMock = vi.fn(async () => response({
      code: 0,
      data: {
        previous_mode: 'develop',
        mode: 'product',
        changed: true,
        scope: 'runtime_session',
        requires_restart: false,
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(switchStartupMode('product', 'develop')).resolves.toEqual({
      previousMode: 'develop',
      mode: 'product',
      changed: true,
      scope: 'runtime_session',
      requiresRestart: false,
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/startup-mode', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ mode: 'product', expected_mode: 'develop' }),
    }))
  })

  it('preserves blocker details from a successful HTTP business error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      code: 3003,
      error: {
        code: 'startup_mode_switch_blocked',
        msg: '存在未结束或未完成清理的任务，不能切换模式',
        details: {
          blockers: [{
            task_uuid: 'task-1',
            workflow_uuid: 'workflow-1',
            status: 'running',
            cleanup_status: 'none',
            execution_kind: 'workflow',
          }],
        },
      },
    })))

    const failure = await switchStartupMode('product', 'develop').catch((error) => error)
    expect(failure).toBeInstanceOf(EdgeApiError)
    expect(failure).toMatchObject({
      code: 'startup_mode_switch_blocked',
      details: { blockers: [{ task_uuid: 'task-1', status: 'running' }] },
    })
    expect(startupModeSwitchBlockers(failure)).toEqual([{
      taskUuid: 'task-1',
      workflowUuid: 'workflow-1',
      status: 'running',
      cleanupStatus: 'none',
      executionKind: 'workflow',
    }])
  })
})

describe('dispenseReagent', () => {
  const completed = {
    command_id: 'cmd-1',
    status: 'completed',
    result: {
      source: { reagent_uuid: 'src', material_uuid: 'm-src', quantity: 50, quantity_unit: 'mL', revision: 2 },
      targets: [{ material_uuid: 'm-1', reagent_uuid: 'r-1', quantity: 50, quantity_unit: 'mL', revision: 1 }],
    },
  }

  it('reads the raw inventory command result instead of the {code,data} envelope', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response(completed))
    vi.stubGlobal('fetch', fetchMock)

    const result = await dispenseReagent({ commandId: 'cmd-1', sourceReagentUuid: 'src', expectedRevision: 1, quantityUnit: 'mL', targets: [{ materialUuid: 'm-1', quantity: 50 }] })

    expect(result.source).toMatchObject({ reagentUuid: 'src', quantity: 50, revision: 2 })
    expect(result.targets).toEqual([{ materialUuid: 'm-1', reagentUuid: 'r-1', quantity: 50, quantityUnit: 'mL', revision: 1 }])
    expect(result.replayed).toBe(false)
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/inventory/commands')
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      command_id: 'cmd-1', type: 'reagent.dispense',
      payload: { source_reagent_uuid: 'src', expected_revision: 1, quantity_unit: 'mL', targets: [{ material_uuid: 'm-1', quantity: 50 }] },
    })
  })

  it('marks an idempotent replay of the same command', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ ...completed, replayed: true })))
    const result = await dispenseReagent({ commandId: 'cmd-1', sourceReagentUuid: 'src', quantityUnit: 'mL', targets: [{ materialUuid: 'm-1', quantity: 50 }] })
    expect(result.replayed).toBe(true)
  })

  it('exposes dispense lineage on reagent rows and history events', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/reagent-history')) {
        return response({ code: 0, data: { items: [
          { uuid: 'h-1', material_uuid: 'm-1', event_type: 'dispense_target', quantity_delta: 30, quantity_unit: 'mL', revision: 1, causation_id: 'cmd-9', changes: { result: { quantity: 30, quantity_unit: 'mL', revision: 1 } }, extension: { source_reagent_uuid: 'src' } },
          { uuid: 'h-2', material_uuid: 'm-src', event_type: 'dispense_source', quantity_delta: -30, quantity_unit: 'mL', revision: 2, causation_id: 'cmd-9', changes: { result: { quantity: 70, quantity_unit: 'mL', revision: 2 } }, extension: { target_reagent_uuids: ['r-1'] } },
        ], total: 2, page: 1, page_size: 100 } })
      }
      return response({ code: 0, data: { items: [
        { uuid: 'r-1', material_uuid: 'm-1', reagent_info_uuid: 'info', name: '乙醇', quantity: 30, quantity_unit: 'mL', revision: 1, meta_data: { source_reagent_uuid: 'src', dispense_command_id: 'cmd-9' } },
        { uuid: 'src', material_uuid: 'm-src', reagent_info_uuid: 'info', name: '乙醇', quantity: 70, quantity_unit: 'mL', revision: 2, meta_data: {} },
      ], total: 2, page: 1, page_size: 100 } })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { loadReagents } = await import('./edgeClient')
    const rows = await loadReagents()
    expect(rows.find((row) => row.uuid === 'r-1')).toMatchObject({ sourceReagentUuid: 'src', dispenseCommandId: 'cmd-9' })
    expect(rows.find((row) => row.uuid === 'src')?.sourceReagentUuid).toBeUndefined()

    const history = await loadReagentHistory('m-1')
    expect(history[0]).toMatchObject({ eventType: 'dispense_target', causationId: 'cmd-9', sourceReagentUuid: 'src' })
    expect(history[1]).toMatchObject({ eventType: 'dispense_source', causationId: 'cmd-9', targetReagentUuids: ['r-1'] })
  })

  it('surfaces a business rejection with the server reason', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ command_id: 'cmd-2', status: 'rejected', error: 'dispense total 999.0 exceeds source quantity 100.0', error_code: '1000' })))
    await expect(dispenseReagent({ commandId: 'cmd-2', sourceReagentUuid: 'src', quantityUnit: 'mL', targets: [{ materialUuid: 'm-1', quantity: 999 }] }))
      .rejects.toThrow('exceeds source quantity')
  })
})

describe('loadWorkflowTaskGraph', () => {
  it('loads the exact frozen workflow revision from a task snapshot', async () => {
    const fetchMock = vi.fn(async () => response({
      code: 0,
      data: {
        uuid: 'task-1',
        workflow_snapshot: {
          workflow: { uuid: 'wf-1', name: '冻结流程', revision: 4 },
          nodes: [{ uuid: 'node-1', name: '冻结节点', type: 'ILab' }],
          edges: [],
        },
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const graph = await loadWorkflowTaskGraph('task-1')

    expect(graph.workflow).toMatchObject({ uuid: 'wf-1', revision: 4 })
    expect(graph.nodes[0]).toMatchObject({ uuid: 'node-1', name: '冻结节点' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workflow-tasks/task-1',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
  })
})

describe('loadWorkflowTaskDetail', () => {
  it('loads heavy node evidence only for the selected task', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/workflow-tasks/task-1')) return response({
        code: 0,
        data: {
          uuid: 'task-1',
          workflow_uuid: 'wf-1',
          status: 'running',
          input: { sample_id: 'sample-1' },
          workflow_snapshot: { workflow: { uuid: 'wf-1', name: '详情流程', revision: 2 } },
          execution_plan: {
            nodes: [{ uuid: 'node-1', name: '称量', topological_index: 0 }],
            edges: [],
          },
        },
      })
      if (url.endsWith('/workflow-tasks/task-1/jobs')) return response({
        code: 0,
        data: [{
          uuid: 'job-1', workflow_node_uuid: 'node-1', status: 'running',
          param: { target: 1.2 }, feedback_data: { actual: 0.8 }, return_info: {},
          error_info: [],
        }],
      })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const task = await loadWorkflowTaskDetail('task-1', [])

    expect(task.nodes[0].job).toMatchObject({
      uuid: 'job-1',
      param: { target: 1.2 },
      feedbackData: { actual: 0.8 },
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

describe('工作流控制节点模板', () => {
  it('将条件和循环节点从设备 Action 目录中分离，并读取参数说明', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/workflow-node-templates?')) return response({ code: 0, data: { items: [
        { uuid: 'action-1', name: 'transfer', display_name: '输送', type: 'UniLabJsonCommand', node_type: 'device_action', resource_template: { uuid: 'pump', name: 'pump', display_name: '注射泵' } },
        { uuid: 'condition-1', name: 'condition', display_name: '条件', type: 'condition', node_type: 'condition', resource_template: { uuid: 'host', name: 'host_node', display_name: '工作流控制' } },
      ], has_more: false } })
      if (url.endsWith('/workflow-node-templates/condition-1')) return response({ code: 0, data: { template: { meta_data: { unilab: { parameter_schema: { type: 'object', description: '条件参数' } } } }, handles: [] } })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(loadActionTemplates()).resolves.toHaveLength(1)
    await expect(loadControlTemplates()).resolves.toEqual([expect.objectContaining({
      uuid: 'condition-1', nodeType: 'condition', parameterSchema: { type: 'object', description: '条件参数' },
    })])
  })
})

describe('createWorkflowTask', () => {
  it('sends normal by default and accepts an explicit high priority', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => (
      response({ code: 0, data: { uuid: 'task-1' } })
    ))
    vi.stubGlobal('fetch', fetchMock)

    await createWorkflowTask({ workflowUuid: 'wf-1', input: {}, description: '' })
    await createWorkflowTask({ workflowUuid: 'wf-1', input: {}, description: '', priority: 'high' })

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      priority: 'normal',
    })
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({
      priority: 'high',
    })
  })
})

describe('loadWorkflowGraph', () => {
  it('preserves scheduler control node kinds for the topology projection', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      code: 0,
      data: {
        workflow: { uuid: 'wf-control', name: '控制流', revision: 1 },
        nodes: [
          { uuid: 'condition', name: '条件', type: 'condition', param: { branches: [] } },
          { uuid: 'repeat', name: '重复直到', type: 'repeat_until', param: { node_uuids: [] } },
        ],
        edges: [],
      },
    })))

    const graph = await loadWorkflowGraph('wf-control')

    expect(graph.nodes.map((node) => node.kind)).toEqual(['condition', 'repeat_until'])
  })
})

describe('Edge view model adapters', () => {
  it('writes reagent identity and container inventory through distinct contracts', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => response({ code: 0, data: { uuid: init?.method === 'POST' ? 'created' : 'other' } }))
    vi.stubGlobal('fetch', fetchMock)

    await createReagentInfo({ name: '乙醇', cas: '64-17-5', aliases: ['酒精'], physicalState: 'liquid' })
    await createReagent({ materialUuid: 'material-1', reagentInfoUuid: 'info-1', quantity: 500, quantityUnit: 'mL', concentrationValue: 95, concentrationUnit: '%' })

    expect(String(fetchMock.mock.calls[0][0])).toContain('/reagent-infos')
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({ name: '乙醇', cas: '64-17-5', physical_state: 'liquid' })
    expect(String(fetchMock.mock.calls[1][0])).toContain('/reagents')
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({ material_uuid: 'material-1', reagent_info_uuid: 'info-1', quantity: 500, quantity_unit: 'mL', concentration_value: 95, concentration_unit: '%' })
  })

  it('instantiates a material directly into the selected site', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ code: 0, data: { uuid: 'material-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await instantiateMaterial({ resourceTemplateUuid: 'template-1', name: '样品瓶', barcode: 'B-001', siteUuid: 'site-1' })

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      resource_template_uuid: 'template-1',
      name: '样品瓶',
      barcode: 'B-001',
      site_placement: { action: 'place', site_uuid: 'site-1' },
    })
  })

  it('deletes a reagent catalog item through its stable UUID', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ code: 0 }))
    vi.stubGlobal('fetch', fetchMock)
    await deleteReagentInfo('info-1')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/reagent-infos/info-1')
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE')
  })

  it('loads the immutable reagent ledger for a container material', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => response({ code: 0, data: { items: [{
      uuid: 'history-1', material_uuid: 'material-1', subject_uuid: 'reagent-1', event_type: 'add',
      operator_type: 'frontend', quantity_delta: 500, quantity_unit: 'mL', revision: 1,
      recorded_at: '2026-09-02T01:02:03.000Z', changes: { result: { quantity: 500, quantity_unit: 'mL' } },
      extension: { source: 'frontend:workbench' },
    }], has_more: false } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(loadReagentHistory('material-1')).resolves.toEqual([expect.objectContaining({
      uuid: 'history-1', materialUuid: 'material-1', reagentUuid: 'reagent-1', eventType: 'add',
      quantityDelta: 500, quantityUnit: 'mL', resultQuantity: 500, source: 'frontend:workbench',
    })])
    expect(String(fetchMock.mock.calls[0][0])).toContain('/materials/material-1/reagent-history')
  })

  it('decodes CAS lookup fields and preserves chemistry metadata when creating a catalog item', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes('/compounds/')) return response({ code: 0, data: { cas: '64-17-5', status: 'ok', compound: { name: 'Ethanol', molecular_formula: 'C2H6O', smiles: 'CCO', inchi_key: 'KEY', molecular_weight: 46.07 } } })
      return response({ code: 0, data: { uuid: 'info-1' } })
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(lookupCompoundByCas('64-17-5')).resolves.toMatchObject({ status: 'ok', compound: { name: 'Ethanol', molecularFormula: 'C2H6O', smiles: 'CCO', inchiKey: 'KEY', molecularWeight: 46.07 } })
    await createReagentInfo({ name: '乙醇', cas: '64-17-5', aliases: ['酒精'], physicalState: 'liquid', smiles: 'CCO', inchiKey: 'KEY', metadata: { custom_parameters: [{ name: '等级', value: '分析纯' }] } })
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({ smiles: 'CCO', inchi_key: 'KEY', meta_data: { custom_parameters: [{ name: '等级', value: '分析纯' }] } })
  })

  it('saves an experiment operation as source and links nodes using returned node UUIDs', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/workflows') && init?.method === 'POST') return response({ code: 0, data: { uuid: 'operation-1', revision: 1 } })
      if (url.endsWith('/workflows/operation-1') && init?.method === 'PUT') return response({ code: 0, data: { uuid: 'operation-1', revision: 1 } })
      if (url.endsWith('/workflow-node-templates/template-1')) return response({ code: 0, data: { template: { uuid: 'template-1', node_type: 'compute', type: 'UniLabJsonCommand' }, handles: [{ uuid: 'ready-source', handle_key: 'ready', io_type: 'source' }, { uuid: 'ready-target', handle_key: 'ready', io_type: 'target' }] } })
      if (url.endsWith('/workflows/operation-1/edges') && init?.method === 'POST') return response({ code: 0, data: { workflow: { uuid: 'operation-1', revision: 4 }, nodes: [], edges: [{ uuid: 'edge-1' }] } })
      if (url.endsWith('/workflows/operation-1/graph')) return response({ code: 0, data: { workflow: { uuid: 'operation-1', revision: 2 }, nodes: [], edges: [] } })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const saved = await createExperimentOperation({
      name: '移液操作', description: '', actions: [{ templateUuid: 'template-1', materialUuid: 'device-1', deviceId: 's09_station', name: '吸液' }, { templateUuid: 'template-1', materialUuid: 'device-1', deviceId: 's09_station', name: '放液' }],
    })

    expect(saved).toMatchObject({ workflowUuid: 'operation-1', revision: 2, status: 'source' })
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/workflows/operation-1/publications'))).toBe(false)
    const graphCall = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith('/workflows/operation-1/graph') && init?.method === 'PUT')
    const graphBody = JSON.parse(String(graphCall?.[1]?.body))
    expect(graphBody.nodes).toHaveLength(2)
    expect(graphBody.nodes[0]).toMatchObject({ material_uuid: 'device-1', description: '吸液', meta_data: { unilab: { executor_binding: { mode: 'fixed', device_id: 'device-1' } } } })
    const edgeCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/workflows/operation-1/edges'))
    const edgeBody = JSON.parse(String(edgeCall?.[1]?.body))
    expect(edgeBody.source_node_uuid).toBe(graphBody.nodes[0].uuid)
    expect(edgeBody.target_node_uuid).toBe(graphBody.nodes[1].uuid)
  })

  it('writes manual confirmation as a wrapper around an ILab action template', async () => {
    let graphBody: Record<string, any> | undefined
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/workflows') && init?.method === 'POST') return response({ code: 0, data: { uuid: 'operation-manual-1', revision: 1 } })
      if (url.endsWith('/workflow-node-templates/template-manual')) return response({ code: 0, data: {
        template: { uuid: 'template-manual', node_type: 'ILab', name: 'transfer_resource', type: 'UniLabJsonCommand' },
        handles: [{ uuid: 'ready-source', handle_key: 'ready', io_type: 'source' }, { uuid: 'ready-target', handle_key: 'ready', io_type: 'target' }],
      } })
      if (url.endsWith('/workflows/operation-manual-1/graph') && init?.method === 'PUT') {
        graphBody = JSON.parse(String(init.body)) as Record<string, any>
        return response({ code: 0, data: { workflow: { uuid: 'operation-manual-1', revision: 2 } } })
      }
      if (url.endsWith('/workflows/operation-manual-1/graph')) return response({ code: 0, data: { workflow: { uuid: 'operation-manual-1', revision: 2 }, nodes: graphBody?.nodes || [], edges: [] } })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await createExperimentOperation({
      name: '人工确认动作', description: '',
      actions: [{ templateUuid: 'template-manual', nodeType: 'ILab', materialUuid: 'device-1', deviceId: 'device-1', name: '确认后转移', param: {}, inputBindings: {}, manualConfirmation: { timeoutSeconds: 45 } }],
    })

    expect(graphBody?.nodes[0]).toMatchObject({
      type: 'manual_confirm',
      manual_confirmation: { timeout_seconds: 45 },
      workflow_node_template_uuid: 'template-manual',
    })
  })

  it('binds an exposed output to the matching action output handle', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/workflows') && init?.method === 'POST') return response({ code: 0, data: { uuid: 'operation-output-1', revision: 1 } })
      if (url.endsWith('/workflow-node-templates/template-output')) return response({ code: 0, data: {
        template: { uuid: 'template-output', node_type: 'ILab', type: 'UniLabJsonCommand', class: 'szlab.devices:Camera' },
        handles: [
          { uuid: 'ready-source', handle_key: 'ready', io_type: 'source' },
          { uuid: 'ready-target', handle_key: 'ready', io_type: 'target' },
          { uuid: 'success-source', handle_key: 'success', data_key: 'success', io_type: 'source', type: 'boolean' },
        ],
      } })
      if (url.endsWith('/workflows/operation-output-1/graph')) return response({ code: 0, data: { workflow: { uuid: 'operation-output-1', revision: 1 }, nodes: [], edges: [] } })
      if (url.endsWith('/workflows/operation-output-1') && init?.method === 'PUT') return response({ code: 0, data: { uuid: 'operation-output-1', revision: 2 } })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await createExperimentOperation({
      name: '带输出合同的操作', description: '',
      outputContract: { version: 1, outputs: [{ name: 'success', schema: { type: 'boolean' }, implicit: false }] },
      actions: [{ templateUuid: 'template-output', materialUuid: 'camera-1', deviceId: 'camera-1', name: '拍照', param: {}, inputBindings: {} }],
    })

    const metadataCall = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith('/workflows/operation-output-1') && init?.method === 'PUT')
    expect(JSON.parse(String(metadataCall?.[1]?.body))).toMatchObject({ meta_data: { unilab: { output_bindings: { success: { kind: 'node_output', workflow_node_uuid: expect.any(String), source_handle_uuid: 'success-source' } } } } })
  })

  /** 验证保存实验操作时写入真实数据句柄，并继续建立 ready 顺序边。 */
  it('persists an upstream action output as a workflow data edge', async () => {
    let graphBody: Record<string, any> | undefined
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/workflows') && init?.method === 'POST') return response({ code: 0, data: { uuid: 'operation-data-1', revision: 1 } })
      if (url.endsWith('/workflow-node-templates/template-source')) return response({ code: 0, data: {
        template: { uuid: 'template-source', node_type: 'compute', type: 'UniLabJsonCommand' },
        handles: [
          { uuid: 'ready-source-1', handle_key: 'ready', io_type: 'source' },
          { uuid: 'ready-target-1', handle_key: 'ready', io_type: 'target' },
          { uuid: 'output-sample', handle_key: 'sample_id', data_key: 'sample_id', io_type: 'source', type: 'string' },
        ],
      } })
      if (url.endsWith('/workflow-node-templates/template-target')) return response({ code: 0, data: {
        template: { uuid: 'template-target', node_type: 'compute', type: 'UniLabJsonCommand' },
        handles: [
          { uuid: 'ready-source-2', handle_key: 'ready', io_type: 'source' },
          { uuid: 'ready-target-2', handle_key: 'ready', io_type: 'target' },
          { uuid: 'input-sample', handle_key: 'sample_id', data_key: 'sample_id', io_type: 'target', required: true, type: 'string' },
        ],
      } })
      if (url.endsWith('/workflows/operation-data-1/graph') && init?.method === 'PUT') {
        graphBody = JSON.parse(String(init.body)) as Record<string, any>
        return response({ code: 0, data: { workflow: { uuid: 'operation-data-1', revision: 2 } } })
      }
      if (url.endsWith('/workflows/operation-data-1/graph') && (!init?.method || init.method === 'GET')) return response({ code: 0, data: { workflow: { uuid: 'operation-data-1', revision: 1 }, nodes: [], edges: graphBody?.edges || [] } })
      if (url.endsWith('/workflows/operation-data-1/edges') && init?.method === 'POST') return response({ code: 0, data: { workflow: { uuid: 'operation-data-1', revision: 3 }, edges: [] } })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await createExperimentOperation({
      name: '上游输出传递', description: '',
      actions: [
        { draftId: 'first', templateUuid: 'template-source', materialUuid: 'device-1', deviceId: 'device-1', name: '产出样品', param: {}, inputBindings: {} },
        { draftId: 'second', templateUuid: 'template-target', materialUuid: 'device-2', deviceId: 'device-2', name: '使用样品', param: {}, inputBindings: { 'input-sample': { kind: 'node_output', sourceNodeId: 'first', sourceHandleUuid: 'output-sample' } } },
      ],
    })

    expect(graphBody?.edges).toEqual([expect.objectContaining({
      source_node_uuid: graphBody?.nodes[0].uuid,
      target_node_uuid: graphBody?.nodes[1].uuid,
      source_handle_uuid: 'output-sample',
      target_handle_uuid: 'input-sample',
      meta_data: { unilab: { generated_by: 'operation-builder', edge_kind: 'data' } },
    })])
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith('/workflows/operation-data-1/edges') && init?.method === 'POST' && String(init.body).includes('ready-source-1'))).toBe(true)
  })

  /**
   * 证明编辑节点输入来源时会替换旧的数据边，同时保留原有 ready 顺序边。
   * 这能防止一个输入句柄在重复编辑后同时连接多个上游输出。
   */
  it('replaces a generated data edge without removing the ready sequence edge', async () => {
    let savedGraph: Record<string, any> | undefined
    const initialGraph = {
      workflow: { uuid: 'wf-data-edit', revision: 4 },
      nodes: [
        { uuid: 'source-node', workflow_node_template_uuid: 'template-source', meta_data: { unilab: { sequence_index: 0 } } },
        { uuid: 'target-node', workflow_node_template_uuid: 'template-target', meta_data: { unilab: { sequence_index: 1 } } },
      ],
      edges: [
        { uuid: 'ready-edge', source_node_uuid: 'source-node', target_node_uuid: 'target-node', source_handle_uuid: 'ready-source', target_handle_uuid: 'ready-target', meta_data: { unilab: { generated_by: 'operation-builder' } } },
        { uuid: 'old-data-edge', source_node_uuid: 'source-node', target_node_uuid: 'target-node', source_handle_uuid: 'old-output', target_handle_uuid: 'target-input', meta_data: { unilab: { generated_by: 'operation-builder', edge_kind: 'data' } } },
      ],
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/workflows/wf-data-edit') && init?.method === 'PUT') return response({ code: 0, data: { uuid: 'wf-data-edit' } })
      if (url.endsWith('/workflows/wf-data-edit/graph') && init?.method === 'PUT') {
        savedGraph = JSON.parse(String(init.body)) as Record<string, any>
        return response({ code: 0, data: { workflow: { uuid: 'wf-data-edit', revision: 5 } } })
      }
      if (url.endsWith('/workflows/wf-data-edit/graph')) return response({ code: 0, data: savedGraph
        ? { workflow: { uuid: 'wf-data-edit', revision: 5 }, nodes: savedGraph.nodes, edges: savedGraph.edges }
        : initialGraph })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await updateExperimentOperation({
      workflowUuid: 'wf-data-edit', name: '修改数据来源', description: '',
      actions: [
        { draftId: 'source-draft', nodeUuid: 'source-node', templateUuid: 'template-source', materialUuid: 'device-1', deviceId: 'device-1', name: '来源动作', param: {}, inputBindings: {} },
        { draftId: 'target-draft', nodeUuid: 'target-node', templateUuid: 'template-target', materialUuid: 'device-2', deviceId: 'device-2', name: '目标动作', param: {}, inputBindings: { 'target-input': { kind: 'node_output', sourceNodeId: 'source-draft', sourceHandleUuid: 'new-output' } } },
      ],
    })

    expect(savedGraph?.edges).toEqual([
      expect.objectContaining({ uuid: 'ready-edge', source_handle_uuid: 'ready-source', target_handle_uuid: 'ready-target' }),
      expect.objectContaining({ source_handle_uuid: 'new-output', target_handle_uuid: 'target-input', meta_data: { unilab: { generated_by: 'operation-builder', edge_kind: 'data' } } }),
    ])
  })

  it('keeps the previous new node template when editing multiple actions', async () => {
    const edgeBodies: Record<string, unknown>[] = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/workflows/wf-1') && init?.method === 'PUT') return response({ code: 0, data: { uuid: 'wf-1' } })
      if (url.endsWith('/workflows/wf-1/graph') && (!init?.method || init.method === 'GET')) return response({ code: 0, data: {
        workflow: { uuid: 'wf-1', revision: 2 }, nodes: [{ uuid: 'existing', workflow_node_template_uuid: 'template-0', meta_data: { unilab: { sequence_index: 0 } } }], edges: [],
      } })
      if (url.endsWith('/workflows/wf-1/graph') && init?.method === 'PUT') return response({ code: 0, data: { uuid: 'wf-1' } })
      if (url.endsWith('/workflow-node-templates/template-1')) return response({ code: 0, data: { handles: [{ uuid: 'source-1', handle_key: 'ready', io_type: 'source' }, { uuid: 'target-1', handle_key: 'ready', io_type: 'target' }] } })
      if (url.endsWith('/workflow-node-templates/template-2')) return response({ code: 0, data: { handles: [{ uuid: 'source-2', handle_key: 'ready', io_type: 'source' }, { uuid: 'target-2', handle_key: 'ready', io_type: 'target' }] } })
      if (url.endsWith('/workflow-node-templates/template-0')) return response({ code: 0, data: { handles: [{ uuid: 'source-0', handle_key: 'ready', io_type: 'source' }, { uuid: 'target-0', handle_key: 'ready', io_type: 'target' }] } })
      if (url.endsWith('/workflows/wf-1/nodes') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as { workflow_node_template_uuid: string }
        return response({ code: 0, data: { uuid: body.workflow_node_template_uuid === 'template-1' ? 'new-1' : 'new-2', workflow_node_template_uuid: body.workflow_node_template_uuid } })
      }
      if (url.endsWith('/workflows/wf-1/edges') && init?.method === 'POST') {
        edgeBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>)
        return response({ code: 0, data: { uuid: 'edge-1' } })
      }
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await updateExperimentOperation({
      workflowUuid: 'wf-1', name: '编辑', description: '',
      actions: [
        { nodeUuid: 'existing', templateUuid: 'template-0', materialUuid: 'device', deviceId: 'device', name: '已有', param: {}, inputBindings: {} },
        { templateUuid: 'template-1', materialUuid: 'device', deviceId: 'device', name: '新增一', param: {}, inputBindings: {} },
        { templateUuid: 'template-2', materialUuid: 'device', deviceId: 'device', name: '新增二', param: {}, inputBindings: {} },
      ],
    })

    const graphUpdate = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith('/workflows/wf-1/graph') && init?.method === 'PUT')
    expect(JSON.parse(String(graphUpdate?.[1]?.body)).nodes[0].meta_data.unilab.executor_binding).toEqual({ mode: 'fixed', device_id: 'device' })
    expect(edgeBodies).toHaveLength(2)
    expect(edgeBodies[0]).toMatchObject({ source_node_uuid: 'existing', source_handle_uuid: 'source-0', target_node_uuid: 'new-1', target_handle_uuid: 'target-1' })
    expect(edgeBodies[1]).toMatchObject({ source_node_uuid: 'new-1', source_handle_uuid: 'source-1', target_node_uuid: 'new-2', target_handle_uuid: 'target-2' })
  })

  it('保存已有条件节点的结构参数并保留其控制元数据', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/workflows/wf-control') && init?.method === 'PUT') return response({ code: 0, data: { uuid: 'wf-control' } })
      if (url.endsWith('/workflows/wf-control/graph') && (!init?.method || init.method === 'GET')) return response({ code: 0, data: {
        workflow: { uuid: 'wf-control', revision: 3 }, nodes: [{ uuid: 'control-1', type: 'condition', name: '条件', workflow_node_template_uuid: 'condition-template', param: { branches: [] }, meta_data: { unilab: { executor_kind: 'condition', source: 'python' } } }], edges: [],
      } })
      if (url.endsWith('/workflows/wf-control/graph') && init?.method === 'PUT') return response({ code: 0, data: { uuid: 'wf-control', revision: 4 } })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await updateExperimentOperation({
      workflowUuid: 'wf-control', name: '条件流程', description: '', actions: [],
      controls: [{ nodeUuid: 'control-1', templateUuid: 'condition-template', name: '按检测结果分支', param: { variables: { qualified: true }, bindings: { qualified: { kind: 'workflow_input' } }, branches: [{ label: '通过', condition: { var: 'qualified' }, node_uuids: ['node-pass'], entry_node_uuids: ['node-pass'], exit_node_uuids: ['node-pass'] }] } }],
    })

    const graphUpdate = fetchMock.mock.calls.find(([calledUrl, calledInit]) => String(calledUrl).endsWith('/workflows/wf-control/graph') && calledInit?.method === 'PUT')
    const body = JSON.parse(String(graphUpdate?.[1]?.body))
    expect(body.nodes[0]).toMatchObject({ name: '按检测结果分支', type: 'condition', param: { variables: { qualified: true } }, meta_data: { unilab: { executor_kind: 'condition', source: 'python' } } })
  })

  it('deletes the just-created operation when a creation step fails', async () => {
    const methods: string[] = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (init?.method) methods.push(`${init.method} ${url}`)
      if (url.endsWith('/workflows') && init?.method === 'POST') return response({ code: 0, data: { uuid: 'wf-failed', revision: 1 } })
      if (url.endsWith('/workflows/wf-failed') && init?.method === 'PUT') return response({ code: 0, data: { uuid: 'wf-failed', revision: 1 } })
      if (url.endsWith('/workflow-node-templates/template-1')) return response({ code: 0, data: { handles: [] } })
      if (url.endsWith('/workflows/wf-failed/graph') && (!init?.method || init.method === 'GET')) return response({ code: 0, data: { workflow: { uuid: 'wf-failed', revision: 2 }, nodes: [], edges: [] } })
      if (url.endsWith('/workflows/wf-failed/graph') && init?.method === 'PUT') return response({ code: 0, data: { workflow: { uuid: 'wf-failed', revision: 3 }, nodes: [], edges: [] } })
      if (url.endsWith('/workflows/wf-failed') && init?.method === 'DELETE') return response({ code: 0 })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(createExperimentOperation({ name: '失败回滚', description: '', actions: [
      { templateUuid: 'template-1', deviceId: 'device', name: '动作', param: {}, inputBindings: {} },
      { templateUuid: 'template-1', deviceId: 'device', name: '动作二', param: {}, inputBindings: {} },
    ] })).rejects.toThrow('ready')
    expect(methods.some((method) => method.startsWith('DELETE ') && method.endsWith('/workflows/wf-failed'))).toBe(true)
  })

  it('adapts workflow metadata and contracts', () => {
    const workflow = adaptWorkflow({
      uuid: 'wf-1',
      name: 'S06 加液生产流程',
      revision: 2,
      status: 'source',
      description: '加液流程',
      meta_data: {
        unilab: {
          input_contract: {
            parameters: [{ name: 'volume', required: true, default: 8, schema: { type: 'integer' } }],
          },
          output_contract: { outputs: [{ name: 'result', schema: { type: 'string' } }] },
          source_bootstrap: { relative_path: 'workflows/s06.py' },
        },
      },
      nodes: [{ uuid: 'node-1' }],
    })

    expect(workflow).toMatchObject({
      uuid: 'wf-1',
      name: 'S06 加液生产流程',
      revision: 2,
      nodeCount: 1,
      sourcePath: 'workflows/s06.py',
    })
    expect(workflow.inputContract[0]).toEqual({
      name: 'volume',
      type: 'integer',
      required: true,
      defaultValue: 8,
      schema: { type: 'integer' },
    })
  })

  it('derives task node state and progress from authoritative jobs', () => {
    const task = adaptTask(
      {
        uuid: 'task-1',
        workflow_uuid: 'wf-1',
        status: 'running',
        priority: 'high',
        description: '联调任务',
        input: { sample_id: 'sample-1' },
        update_time: '2026-08-31T18:00:00Z',
        execution_plan: {
          nodes: [
            { uuid: 'node-1', kind: 'workflow_input', topological_index: 0 },
            { uuid: 'node-2', kind: 'device_action', action_name: 'add_liquid', device_id: 'S06', topological_index: 1 },
            { uuid: 'node-3', kind: 'workflow_output', topological_index: 2 },
          ],
        },
      },
      [
        { workflow_node_uuid: 'node-1', status: 'succeeded', topological_index: 0 },
        { workflow_node_uuid: 'node-2', status: 'running', topological_index: 1 },
      ],
      'S06 加液生产流程',
    )

    expect(task.progress).toBe(33)
    expect(task.priority).toBe('high')
    expect(task.current).toBe('add_liquid')
    expect(task.nodes.map((node) => node.status)).toEqual(['succeeded', 'running', 'pending'])
  })

  it('preserves legacy numeric task priority instead of silently relabeling it', () => {
    const task = adaptTask(
      {
        uuid: 'task-legacy-priority',
        workflow_uuid: 'wf-1',
        status: 'succeeded',
        priority: 50,
        execution_plan: { nodes: [] },
      },
      [],
      '测试工作流',
    )

    expect(task.priority).toBe(50)
  })

  it('projects a safe SigNoz trace reference from the task response', () => {
    const rawTask = {
      uuid: 'task-traced',
      workflow_uuid: 'wf-1',
      status: 'running',
      trace_context: {
        trace_id: '0123456789abcdef0123456789abcdef',
      },
      execution_plan: { nodes: [] },
    }
    const task = adaptTask(
      rawTask,
      [],
      '测试工作流',
      [],
      undefined,
      'http://127.0.0.1:30081',
    )
    const unsafe = adaptTask(rawTask, [], '测试工作流', [], undefined, 'javascript:alert(1)')

    expect(task.trace).toEqual({
      traceId: '0123456789abcdef0123456789abcdef',
      url: 'http://127.0.0.1:30081/trace/0123456789abcdef0123456789abcdef',
      mode: 'trace',
    })
    expect(unsafe.trace).toBeUndefined()
  })

  it('links historical tasks without a persisted trace id to a task-filtered scheduler search', () => {
    const task = adaptTask(
      {
        uuid: '21000000-0000-4000-8000-000000000001',
        workflow_uuid: 'wf-1',
        status: 'succeeded',
        trace_context: {},
        execution_plan: { nodes: [] },
      },
      [],
      '测试工作流',
      [],
      undefined,
      'http://127.0.0.1:30081',
    )

    expect(task.trace?.mode).toBe('search')
    expect(task.trace?.traceId).toBeUndefined()
    expect(task.trace?.url).toContain('/traces-explorer?compositeQuery=')
    expect(decodeURIComponent(decodeURIComponent(new URL(task.trace!.url).searchParams.get('compositeQuery')!)))
      .toContain('21000000-0000-4000-8000-000000000001')
  })

  it('projects authoritative job input, feedback, result, and errors onto each task node', () => {
    const task = adaptTask(
      {
        uuid: 'task-node-evidence',
        workflow_uuid: 'wf-1',
        status: 'failed',
        execution_plan: {
          nodes: [{ uuid: 'node-1', name: 'S07 投粉', kind: 'device_action', topological_index: 0 }],
        },
      },
      [{
        uuid: 'job-1',
        workflow_node_uuid: 'node-1',
        status: 'failed',
        attempt: 2,
        param: { target_mass_g: 1.2 },
        feedback_data: { current_mass_g: 0.8 },
        return_info: { success: false, actual_mass_g: 0.81 },
        error_info: [{ code: 'mass_out_of_range' }],
        started_at: '2026-09-02T01:00:00Z',
        finished_at: '2026-09-02T01:00:03Z',
      }],
    )

    expect(task.nodes[0].job).toMatchObject({
      uuid: 'job-1',
      attempt: 2,
      param: { target_mass_g: 1.2 },
      feedbackData: { current_mass_g: 0.8 },
      returnInfo: { success: false, actual_mass_g: 0.81 },
      errorInfo: [{ code: 'mass_out_of_range' }],
      startedAt: '2026-09-02T01:00:00Z',
      finishedAt: '2026-09-02T01:00:03Z',
    })
  })

  it('projects a pending manual confirmation onto the corresponding job and highlights it', () => {
    const task = adaptTask(
      {
        uuid: 'task-manual',
        workflow_uuid: 'wf-1',
        status: 'running',
        execution_plan: {
          nodes: [{ uuid: 'manual-node', name: '现场确认', kind: 'manual_confirm' }],
        },
      },
      [{
        uuid: 'manual-job',
        workflow_node_uuid: 'manual-node',
        status: 'running',
        manual_confirmation: {
          status: 'pending',
          deadline_at: '2099-01-01T00:00:00Z',
          actions: ['approve', 'reject'],
        },
      }],
    )

    expect(task.nodes[0].status).toBe('attention')
    expect(task.nodes[0].job?.manualConfirmation).toEqual({
      status: 'pending',
      deadlineAt: '2099-01-01T00:00:00Z',
      actions: ['approve', 'reject'],
    })
  })

  it('groups tasks from the same frozen node topology even when snapshot storage metadata differs', () => {
    const base = {
      workflow_uuid: 'wf-1',
      status: 'running',
      workflow_snapshot: {
        workflow: { uuid: 'wf-1', revision: 2 },
        nodes: [{ uuid: 'node-1', name: '投粉' }],
      },
      execution_plan: {
        nodes: [{ uuid: 'node-1', name: '投粉', kind: 'device_action', action_name: 'dose', param: {} }],
        edges: [],
      },
      run_mode: 'normal',
    }
    const first = adaptTask({
      ...base,
      uuid: 'task-1',
      revision_fingerprint: 'old-storage-fingerprint',
      workflow_snapshot: {
        ...base.workflow_snapshot,
        workflow: { ...base.workflow_snapshot.workflow, update_time: '2026-09-01T00:00:00Z' },
      },
    })
    const second = adaptTask({
      ...base,
      uuid: 'task-2',
      revision_fingerprint: 'new-storage-fingerprint',
      workflow_snapshot: {
        ...base.workflow_snapshot,
        workflow: { ...base.workflow_snapshot.workflow, update_time: '2026-09-02T00:00:00Z' },
      },
    })

    expect(first.matrixGroupKey).toBe(second.matrixGroupKey)
  })

  it('preserves skipped, cancellation, and intervention node states', () => {
    const rawTask = {
      uuid: 'task-state-map',
      workflow_uuid: 'wf-1',
      status: 'canceling',
      execution_plan: {
        nodes: [
          { uuid: 'node-1', topological_index: 0 },
          { uuid: 'node-2', topological_index: 1 },
          { uuid: 'node-3', topological_index: 2 },
        ],
      },
    }
    const task = adaptTask(rawTask, [
      { workflow_node_uuid: 'node-1', status: 'skipped' },
      { workflow_node_uuid: 'node-2', status: 'cancel_requested' },
      { workflow_node_uuid: 'node-3', status: 'intervention_required' },
    ])

    expect(task.status).toBe('canceling')
    expect(task.nodes.map((node) => node.status)).toEqual(['skipped', 'canceling', 'attention'])
  })

  it('does not reinterpret a non-contract task status alias', () => {
    expect(adaptTask({ uuid: 'task-alias', status: 'success' }).status).toBe('unknown')
  })

  it('projects wait codes and control holds instead of reporting a task as normally running', () => {
    const blocked = adaptTask({
      uuid: 'task-blocked',
      workflow_uuid: 'wf-1',
      status: 'pending',
      wait_reason: { code: 'global_task_capacity' },
      execution_plan: { nodes: [] },
    })
    const intervention = adaptTask({
      uuid: 'task-intervention',
      workflow_uuid: 'wf-1',
      status: 'running',
      control_status: 'waiting_intervention',
      execution_plan: { nodes: [] },
    })

    expect(blocked).toMatchObject({ status: 'admission_blocked', current: 'global_task_capacity' })
    expect(intervention).toMatchObject({ status: 'intervention_required', current: '等待人工干预' })
  })

  it('lights Job wait reasons and surfaces cleanup attention', () => {
    const task = adaptTask({
      uuid: 'task-cleanup',
      workflow_uuid: 'wf-1',
      status: 'succeeded',
      cleanup_status: 'requires_attention',
      attention_reason: 'inventory_claim_uncertain',
      execution_plan: { nodes: [{ uuid: 'node-1', device_id: 'reactor-a', topological_index: 0 }] },
    }, [
      { workflow_node_uuid: 'node-1', status: 'pending', wait_reason: { code: 'device_lock' } },
    ], '设备等待流程', [], undefined, '', {
      devices: { 'reactor-a': 'S04 反应器' },
    })

    expect(task.status).toBe('intervention_required')
    expect(task.current).toBe('inventory_claim_uncertain')
    expect(task.nodes[0].status).toBe('waiting')
    expect(task.nodes[0].waitReason).toMatchObject({
      title: '等待设备',
      details: ['设备：S04 反应器（reactor-a）'],
    })
  })

  it('presents structured resource waits and derives unresolved upstream dependencies', () => {
    const task = adaptTask({
      uuid: 'task-wait-reasons',
      workflow_uuid: 'wf-1',
      status: 'running',
      execution_plan: {
        nodes: [
          { uuid: 'node-ready', name: '准备烧杯', topological_index: 0 },
          { uuid: 'node-site', name: '转运烧杯', device_id: 'robot-1', topological_index: 1 },
          { uuid: 'node-dependent', name: '加液', topological_index: 2 },
        ],
        edges: [
          { source_node_uuid: 'node-site', target_node_uuid: 'node-dependent' },
        ],
      },
    }, [
      { workflow_node_uuid: 'node-ready', status: 'succeeded', wait_reason: {} },
      {
        workflow_node_uuid: 'node-site',
        status: 'pending',
        wait_reason: {
          code: 'operation_lease',
          message: '执行资源正在被其他作业使用',
          waiting_since: '2026-09-01T09:00:00Z',
          resources: [
            { scope: 'device', device_id: 'robot-1' },
            { scope: 'material_site', material_uuid: 'material-1', site_uuid: 'S0722' },
            { scope: 'material', material_uuid: 'material-1' },
          ],
          blocking_task_uuid: 'task-other',
          blocking_job_uuid: 'job-other',
        },
      },
      { workflow_node_uuid: 'node-dependent', status: 'ready', wait_reason: {} },
    ], '资源等待流程', [], undefined, '', {
      devices: {
        'robot-1': 'S09 机械臂',
      },
      sites: {
        S0722: 'S07 工作站 / 称量位',
      },
      materials: {
        'material-1': '待称量烧杯',
      },
    })

    expect(task.nodes[1].waitReason).toEqual({
      code: 'operation_lease',
      title: '等待执行资源',
      message: '执行资源正在被其他作业使用',
      details: [
        '设备：S09 机械臂（robot-1）',
        '库位：S07 工作站 / 称量位（S0722）',
        '物料：待称量烧杯（material-1）',
        '阻塞任务：task-other',
        '阻塞 Job：job-other',
      ],
      waitingSince: '2026-09-01T09:00:00Z',
    })
    expect(task.nodes[0].waitReason).toBeUndefined()
    expect(task.nodes[2].waitReason).toEqual({
      code: 'upstream_dependency',
      title: '等待前置节点',
      message: '以下节点完成后才能运行',
      details: ['转运烧杯'],
    })
  })

  it('uses wait-resource names carried by the scheduler without a separate inventory lookup', () => {
    const task = adaptTask({
      uuid: 'task-inline-wait-names',
      workflow_uuid: 'wf-1',
      status: 'running',
      execution_plan: {
        nodes: [{ uuid: 'node-wait', name: '等待节点', topological_index: 0 }],
      },
    }, [{
      workflow_node_uuid: 'node-wait',
      status: 'pending',
      wait_reason: {
        code: 'operation_lease',
        resources: [
          {
            scope: 'device',
            device_id: 'device-1',
            device_name: 'S09 机械臂',
          },
          {
            scope: 'material_site',
            material_uuid: 'device-2',
            material_name: 'S08 开盖机',
            site_uuid: 'site-1',
            site_name: 'INPUT-1',
          },
          {
            scope: 'material',
            material_uuid: 'material-1',
            material_name: '样品瓶 A',
          },
        ],
      },
    }])

    expect(task.nodes[0].waitReason?.details).toEqual([
      '设备：S09 机械臂（device-1）',
      '库位：S08 开盖机 / INPUT-1（site-1）',
      '物料：样品瓶 A（material-1）',
    ])
  })

  it('projects a task-level material admission wait onto its material-source nodes', () => {
    const task = adaptTask({
      uuid: 'task-material-admission',
      workflow_uuid: 'wf-1',
      status: 'pending',
      wait_reason: {
        code: 'material_unavailable',
        message: '样品瓶尚未进入目标库位',
        waiting_since: '2026-09-01T10:00:00Z',
      },
      execution_plan: {
        nodes: [
          { uuid: 'node-source', name: '样品瓶准入', kind: 'material_source', topological_index: 0 },
          { uuid: 'node-action', name: '开盖', kind: 'device_action', topological_index: 1 },
        ],
        edges: [{ source_node_uuid: 'node-source', target_node_uuid: 'node-action' }],
      },
    }, [
      { workflow_node_uuid: 'node-source', status: 'pending', executor_kind: 'material_source' },
      { workflow_node_uuid: 'node-action', status: 'pending' },
    ])

    expect(task.nodes[0]).toMatchObject({
      status: 'waiting',
      waitReason: {
        code: 'material_unavailable',
        title: '等待物料',
        message: '样品瓶尚未进入目标库位',
        details: ['物料需求：样品瓶准入（尚未分配具体物料）'],
        waitingSince: '2026-09-01T10:00:00Z',
      },
    })
    expect(task.nodes[1].waitReason).toMatchObject({
      code: 'upstream_dependency',
      details: ['样品瓶准入'],
    })
  })

  it('classifies temporary site candidate failures as library waits', () => {
    const task = adaptTask({
      uuid: 'task-site-wait',
      status: 'running',
      execution_plan: {
        nodes: [
          { uuid: 'node-site', name: '转运', topological_index: 0 },
          { uuid: 'node-site-legacy', name: '回库', topological_index: 1 },
        ],
      },
    }, [
      {
        workflow_node_uuid: 'node-site',
        status: 'pending',
        wait_reason: {
          code: 'site_group_unavailable',
          message: '候选库位当前均不可用',
          resources: [
            { scope: 'material_site', site_uuid: 'S081' },
            { scope: 'material_site', site_uuid: 'S082' },
          ],
        },
      },
      {
        workflow_node_uuid: 'node-site-legacy',
        status: 'pending',
        wait_reason: { code: 'site_occupied', message: '目标库位当前已有物料' },
      },
    ])

    expect(task.nodes[0].waitReason).toMatchObject({
      code: 'site_group_unavailable',
      title: '等待库位',
      details: ['库位：S081', '库位：S082'],
    })
    expect(task.nodes[1].waitReason?.title).toBe('等待库位')
  })

  it('does not describe paused nodes as waiting for scheduler dispatch', () => {
    const task = adaptTask({
      uuid: 'task-paused',
      status: 'pending',
      control_status: 'paused',
      execution_plan: {
        nodes: [{ uuid: 'node-paused', name: '暂停节点', topological_index: 0 }],
        edges: [],
      },
    }, [{ workflow_node_uuid: 'node-paused', status: 'pending' }])

    expect(task.nodes[0].waitReason).toBeUndefined()
  })

  it('keeps terminal task status authoritative over historical paused control state', () => {
    const task = adaptTask({
      uuid: 'task-terminal-step',
      status: 'succeeded',
      execution_mode: 'step',
      control_status: 'paused',
      execution_plan: { nodes: [], edges: [] },
    })

    expect(task.status).toBe('succeeded')
  })

  it('groups only identical frozen task matrix definitions', () => {
    const snapshot = {
      workflow: { uuid: 'wf-1', name: '冻结流程', revision: 3, create_time: '2026-01-01', update_time: '2026-01-01' },
      nodes: [{ uuid: 'node-1', name: '加液', param: { static_mode: 'fast' }, create_time: '2026-01-01' }],
      edges: [],
    }
    const task = (uuid: string, revision = 3, param = { volume: 1 }, edge = false) => adaptTask({
      uuid,
      workflow_uuid: 'wf-1',
      execution_kind: 'workflow',
      status: 'running',
      run_mode: 'normal',
      workflow_snapshot: {
        ...snapshot,
        workflow: { ...snapshot.workflow, revision },
        edges: edge ? [{ uuid: 'edge-1' }] : [],
      },
      execution_plan: {
        version: 1,
        nodes: [{ uuid: 'node-1', kind: 'device_action', topological_index: 0, param }],
        edges: edge ? [{ source_handle_uuid: 'a', target_handle_uuid: 'b' }] : [],
        handles: [],
      },
    })

    expect(task('task-a', 3, { volume: 1 }).matrixGroupKey).toBe(
      task('task-b', 3, { volume: 2 }).matrixGroupKey,
    )
    const reordered = adaptTask({
      run_mode: 'normal',
      status: 'running',
      execution_kind: 'workflow',
      workflow_uuid: 'wf-1',
      uuid: 'task-reordered',
      execution_plan: {
        handles: [],
        edges: [],
        nodes: [{ topological_index: 0, kind: 'device_action', uuid: 'node-1', param: { volume: 9 } }],
        version: 1,
      },
      workflow_snapshot: {
        edges: [],
        nodes: [{ update_time: '2026-09-01', param: { static_mode: 'fast' }, name: '加液', uuid: 'node-1' }],
        workflow: { update_time: '2026-09-01', create_time: '2025-01-01', revision: 3, name: '冻结流程', uuid: 'wf-1' },
      },
    })
    expect(task('task-a', 3).matrixGroupKey).toBe(reordered.matrixGroupKey)
    const reclassified = adaptTask({
      uuid: 'task-reclassified',
      workflow_uuid: 'wf-1',
      execution_kind: 'workflow',
      status: 'running',
      run_mode: 'normal',
      workflow_snapshot: snapshot,
      execution_plan: {
        version: 1,
        nodes: [{ uuid: 'node-1', kind: 'material_transfer', topological_index: 0 }],
        edges: [],
        handles: [],
      },
    })
    expect(task('task-a', 3).matrixGroupKey).toBe(reclassified.matrixGroupKey)
    expect(task('task-a', 3).matrixGroupKey).not.toBe(task('task-b', 4).matrixGroupKey)
    expect(task('task-a', 3).matrixGroupKey).not.toBe(task('task-b', 3, { volume: 1 }, true).matrixGroupKey)
    expect(adaptTask({ uuid: 'task-missing-a' }).matrixGroupKey).not.toBe(
      adaptTask({ uuid: 'task-missing-b' }).matrixGroupKey,
    )
  })

  it('collects exact material UUID references from plans, jobs, and ResourceSlot inputs', () => {
    const task = adaptTask(
      {
        uuid: 'task-materials',
        workflow_uuid: 'wf-1',
        status: 'running',
        input: {
          sample: { uuid: 'material-input' },
          batches: [{ uuid: 'material-input-array-a' }, { uuid: 'material-input-array-b' }],
        },
        execution_plan: {
          nodes: [{
            uuid: 'node-1',
            material_uuid: 'material-plan',
            param: {
              plate: { uuid: 'material-param' },
              tips: [{ uuid: 'material-tip-a' }, { uuid: 'material-tip-b' }],
            },
            param_schema: {
              type: 'object',
              properties: {
                goal: {
                  type: 'object',
                  properties: {
                    plate: { $slot: 'ResourceSlot' },
                    tips: { type: 'array', items: { $slot: 'ResourceSlot' } },
                  },
                },
              },
            },
          }],
        },
      },
      [{
        workflow_node_uuid: 'node-1',
        status: 'running',
        material_uuid: 'material-job',
        control_data: { actual_executor: { material_uuid: 'material-executor' } },
        return_info: { material: { uuid: 'material-result' } },
        expected_change_set: { material_uuid: 'material-change-set' },
        param: { plate: { uuid: 'material-job-param' }, tips: [] },
      }],
      '物料流程',
      [
        { name: 'sample', type: 'ResourceSlot', schema: { $slot: 'ResourceSlot' } },
        { name: 'batches', type: 'array', schema: { type: 'array', items: { $slot: 'ResourceSlot' } } },
      ],
    )

    expect(new Set(task.materialUuids)).toEqual(new Set([
      'material-input',
      'material-input-array-a',
      'material-input-array-b',
      'material-plan',
      'material-param',
      'material-tip-a',
      'material-tip-b',
      'material-job-param',
      'material-job',
      'material-executor',
      'material-result',
      'material-change-set',
    ]))
  })

  it('keeps configured source separate from an unresolved current location', () => {
    const material = adaptMaterial({
      uuid: 'mat-1',
      name: '烧杯 500 mL',
      barcode: 'BKR-001',
      class: 'community.szlab.beaker',
      resource_template_uuid: 'template-beaker',
      update_time: '2026-08-31T18:00:00Z',
      config: { category: 'beaker' },
      meta_data: { source_graph: 'szlab.json', source_node_id: 's3_unused_beaker__L1B4' },
    })

    expect(material).toMatchObject({
      uuid: 'mat-1',
      category: 'beaker',
      configuredSource: 'S3 / L1B4',
      currentLocation: { kind: 'unresolved', label: '权威位置尚未读取' },
      sourceGraph: 'szlab.json',
      resourceTemplateUuid: 'template-beaker',
      taskReferences: [],
    })
  })

  it('uses the current Site authority instead of prefixing it with the original source station', () => {
    const moved = adaptMaterial({
      uuid: 'mat-moved',
      name: '已转运烧杯',
      meta_data: { source_node_id: 's3_unused_beaker__L1B4' },
      current_site: {
        uuid: 'site-s061',
        name: 'S061',
        material_uuid: 'station-s6',
        meta_data: { source_node_id: 's6_buffer' },
      },
    })
    const unassigned = adaptMaterial({
      uuid: 'mat-unassigned',
      name: '待分配烧杯',
      meta_data: { source_node_id: 's3_unused_beaker__L1B4' },
      current_site: null,
    })

    expect(moved.currentLocation).toEqual({
      kind: 'site',
      label: 'S6 / S061',
      siteUuid: 'site-s061',
      ownerMaterialUuid: 'station-s6',
    })
    expect(unassigned.currentLocation).toEqual({
      kind: 'unassigned',
      label: '未分配权威库位',
    })
    const structural = adaptMaterial({
      uuid: 'station-s09',
      name: 'S09移液工位仓',
      config: { logical_mount: true, sites: [{ name: 'BEAKER1' }, { name: 'REAGENT1' }] },
      current_site: null,
    })
    expect(structural.currentLocation).toEqual({
      kind: 'structural',
      label: '结构资源 · 提供 2 个库位',
      siteCount: 2,
    })
    expect(structural.isStructural).toBe(true)
  })
})

describe('loadEdgeSnapshot', () => {
  it('resolves waiting device, site, and material identities to authoritative names', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/readiness')) return response({ status: 'ready' })
      if (url.includes('/workflows?')) {
        return response({ code: 0, data: { items: [{ uuid: 'wf-1', name: '资源等待流程' }], total: 1 } })
      }
      if (url.endsWith('/devices')) {
        return response({
          code: 0,
          data: [{
            binding: {
              local_id: 'robot-1',
              material_uuid: 'device-material-1',
              name: 'S09 机械臂',
            },
            material: { uuid: 'device-material-1', name: '机械臂设备' },
          }],
        })
      }
      if (url.includes('/workflow-task-presentations?view=matrix')) {
        return response({
          code: 0,
          data: {
            items: [{
              uuid: 'task-waiting',
              workflow_uuid: 'wf-1',
              status: 'running',
              execution_plan: {
                nodes: [{ uuid: 'node-transfer', name: '转运样品', topological_index: 0 }],
                edges: [],
              },
              jobs: [{
                workflow_node_uuid: 'node-transfer',
                status: 'pending',
                wait_reason: {
                  code: 'operation_lease',
                  message: '执行资源正在被其他作业使用',
                  resources: [
                    { scope: 'device', device_id: 'device-material-1' },
                    {
                      scope: 'material_site',
                      site_uuid: 'site-s08-open',
                      material_uuid: 'station-s08',
                    },
                    { scope: 'material', material_uuid: 'material-sample' },
                  ],
                },
              }],
            }],
            total: 1,
          },
        })
      }
      if (url.includes('/workflow-task-presentations?')) {
        return response({ code: 0, data: { items: [], total: 0 } })
      }
      if (url.endsWith('/materials/graph')) {
        return response({
          code: 0,
          data: {
            nodes: [
              {
                material: { uuid: 'station-s08', name: 'S08 工作站' },
                current_site_uuid: null,
                sites: [{ uuid: 'site-s08-open', name: '开盖位', material_uuid: 'station-s08' }],
              },
              {
                material: { uuid: 'material-sample', name: '待检样品瓶' },
                current_site_uuid: null,
                sites: [],
              },
            ],
          },
        })
      }
      if (url.includes('/materials?')) {
        return response({
          code: 0,
          data: { items: [{ uuid: 'material-sample', name: '待检样品瓶' }], total: 1 },
        })
      }
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const snapshot = await loadEdgeSnapshot()

    expect(snapshot.tasks[0].nodes[0].waitReason?.details).toEqual([
      '设备：S09 机械臂（device-material-1）',
      '库位：S08 工作站 / 开盖位（site-s08-open）',
      '物料：待检样品瓶（material-sample）',
    ])
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/jobs'))).toBe(false)
  })

  it('joins authoritative Material Graph locations and exact nonterminal task references', async () => {
    const taskRows = [
      {
        uuid: 'task-running',
        workflow_uuid: 'wf-1',
        status: 'running',
        workflow_snapshot: { workflow: { uuid: 'wf-1', name: '物料流程', revision: 1 }, nodes: [], edges: [] },
        execution_plan: { nodes: [{ uuid: 'node-1', material_uuid: 'material-child' }], edges: [], handles: [] },
        jobs: [],
      },
      {
        uuid: 'task-succeeded',
        workflow_uuid: 'wf-1',
        status: 'succeeded',
        workflow_snapshot: { workflow: { uuid: 'wf-1', name: '物料流程', revision: 1 }, nodes: [], edges: [] },
        execution_plan: { nodes: [{ uuid: 'node-1', material_uuid: 'material-child' }], edges: [], handles: [] },
        jobs: [],
      },
    ]
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/readiness')) return response({ status: 'ready' })
      if (url.includes('/workflows?')) {
        return response({ code: 0, data: { items: [{ uuid: 'wf-1', name: '物料流程' }], total: 1 } })
      }
      if (url.includes('/workflow-tasks/task-')) return response({ code: 0, data: [] })
      if (url.includes('/workflow-task-presentations?')) {
        return response({ code: 0, data: { items: taskRows, total: taskRows.length } })
      }
      if (url.endsWith('/materials/graph')) {
        return response({
          code: 0,
          data: {
            nodes: [
              {
                material: { uuid: 'material-owner', name: 'S06 工站' },
                current_site_uuid: null,
                sites: [{ uuid: 'site-s061', name: 'S061', material_uuid: 'material-owner' }],
              },
              {
                material: { uuid: 'material-child', name: '烧杯' },
                current_site_uuid: 'site-s061',
                sites: [],
              },
            ],
          },
        })
      }
      if (url.includes('/materials?')) {
        return response({ code: 0, data: { items: [{ uuid: 'material-child', name: '烧杯' }], total: 1 } })
      }
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const snapshot = await loadEdgeSnapshot()

    expect(snapshot.materials[0].currentLocation).toEqual({
      kind: 'site',
      label: 'S06 工站 / S061',
      siteUuid: 'site-s061',
      ownerMaterialUuid: 'material-owner',
    })
    expect(snapshot.materials[0].taskReferences).toEqual([
      expect.objectContaining({ taskUuid: 'task-running', taskStatus: 'running' }),
    ])
  })

  it('uses compact task material identities when projecting ResourceSlot references', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/readiness')) return response({ status: 'ready' })
      if (url.includes('/workflows?')) {
        return response({
          code: 0,
          data: {
            items: [{
              uuid: 'wf-1',
              name: '当前流程',
              meta_data: { unilab: { input_contract: { parameters: [] } } },
            }],
            total: 1,
          },
        })
      }
      if (url.includes('/workflow-tasks/task-frozen/jobs')) return response({ code: 0, data: [] })
      if (url.includes('/workflow-task-presentations?view=matrix')) {
        return response({
          code: 0,
          data: {
            items: [{
              uuid: 'task-frozen',
              workflow_uuid: 'wf-1',
              status: 'running',
              input: { sample_id: 'sample-1' },
              material_uuids: ['material-frozen'],
              workflow_snapshot: {
                workflow: {
                  uuid: 'wf-1',
                  name: '冻结流程',
                  revision: 1,
                },
                nodes: [],
                edges: [],
              },
              execution_plan: { nodes: [], edges: [], handles: [] },
              jobs: [],
            }],
            total: 1,
          },
        })
      }
      if (url.includes('/workflow-task-presentations?')) return response({ code: 0, data: { items: [], total: 0 } })
      if (url.endsWith('/materials/graph')) {
        return response({ code: 0, data: { nodes: [{ material: { uuid: 'material-frozen' }, sites: [] }] } })
      }
      if (url.includes('/materials?')) {
        return response({ code: 0, data: { items: [{ uuid: 'material-frozen', name: '冻结物料' }], total: 1 } })
      }
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const snapshot = await loadEdgeSnapshot()

    expect(snapshot.materials[0].taskReferences).toEqual([
      expect.objectContaining({ taskUuid: 'task-frozen', workflowName: '冻结流程' }),
    ])
    expect(snapshot.materials[0].currentLocation).toEqual({
      kind: 'unresolved',
      label: '物料图缺少当前位置字段',
    })
  })

  it('follows Edge material pagination and loads the task matrix in one request', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/readiness')) {
        return response({ status: 'ready', workflowProgress: { loaded: 1, total: 1 } })
      }
      if (url.includes('/workflows?')) {
        return response({ code: 0, data: { items: [{ uuid: 'wf-1', name: '测试工作流' }], total: 1, has_more: false } })
      }
      if (url.includes('/workflow-task-presentations?')) {
        return response({ code: 0, data: { items: [], total: 0, has_more: false } })
      }
      if (url.endsWith('/materials/graph')) {
        return response({ code: 0, data: { nodes: [] } })
      }
      if (url.includes('/materials?') && url.includes('page=1')) {
        return response({
          code: 0,
          data: {
            items: Array.from({ length: 100 }, (_, index) => ({ uuid: `material-${index}`, name: `物料 ${index}` })),
            total: 101,
            has_more: true,
          },
        })
      }
      if (url.includes('/materials?') && url.includes('page=2')) {
        return response({ code: 0, data: { items: [{ uuid: 'material-100', name: '物料 100' }], total: 101, has_more: false } })
      }
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const snapshot = await loadEdgeSnapshot()

    expect(snapshot.materials).toHaveLength(101)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/materials?page=2&page_size=100'),
      expect.any(Object),
    )
    const presentationUrls = fetchMock.mock.calls
      .map(([input]) => String(input))
      .filter((url) => url.includes('/workflow-task-presentations?'))
    expect(presentationUrls).toEqual([
      expect.stringContaining('/workflow-task-presentations?view=matrix&terminal_limit=20'),
    ])
  })

  it('fails the snapshot when the authoritative task projection omits Jobs', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/readiness')) return response({ status: 'ready' })
      if (url.includes('/workflows?')) {
        return response({ code: 0, data: { items: [{ uuid: 'wf-1', name: '测试工作流' }], total: 1, has_more: false } })
      }
      if (url.includes('/workflow-task-presentations?')) {
        return response({ code: 0, data: { items: [{ uuid: 'task-1', workflow_uuid: 'wf-1', status: 'running' }], total: 1, has_more: false } })
      }
      if (url.endsWith('/materials/graph')) return response({ code: 0, data: { nodes: [] } })
      if (url.includes('/materials?')) return response({ code: 0, data: { items: [], total: 0, has_more: false } })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(loadEdgeSnapshot()).rejects.toThrow('Edge 任务展示投影缺少 jobs')
  })

  it('times out a shared task projection and allows the next refresh to recover', async () => {
    vi.useFakeTimers()
    let projectionAttempts = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/readiness')) return response({ status: 'ready' })
      if (url.includes('/workflows?')) {
        return response({ code: 0, data: { items: [], total: 0, has_more: false } })
      }
      if (url.includes('/workflow-task-presentations?view=matrix')) {
        projectionAttempts += 1
        if (projectionAttempts === 1) {
          return new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => {
              reject(new DOMException('Aborted', 'AbortError'))
            })
          })
        }
        return response({ code: 0, data: { items: [], total: 0 } })
      }
      if (url.endsWith('/materials/graph')) return response({ code: 0, data: { nodes: [] } })
      if (url.includes('/materials?')) {
        return response({ code: 0, data: { items: [], total: 0, has_more: false } })
      }
      if (url.endsWith('/devices')) return response({ code: 0, data: [] })
      throw new Error(`Unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    try {
      const timedOut = expect(loadEdgeSnapshot()).rejects.toThrow()
      await vi.advanceTimersByTimeAsync(15_000)
      await timedOut

      await expect(loadEdgeSnapshot()).resolves.toMatchObject({ tasks: [] })
      expect(projectionAttempts).toBe(2)
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('loadWorkflowGraph inventory requirements', () => {
  it('maps inventory_requirements compiled from material_source quantities', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ code: 0, data: {
      workflow: { uuid: 'wf-1', name: 'w', revision: 3, status: 'source' },
      nodes: [], edges: [], node_templates: [], handle_templates: [],
      inventory_requirements: [{
        uuid: 'req-1', requirement_key: 'solvent_a', consume_node_uuid: 'node-9', target_type: 'reagent_info',
        reagent_info_uuid: null, required_quantity: 10, quantity_unit: 'mL', allow_split: false,
        meta_data: { unilab: { material_source_node_uuid: 'node-2', quantity_target: 'container_content' } },
      }],
    } })))
    const graph = await loadWorkflowGraph('wf-1')
    expect(graph.inventoryRequirements).toEqual([{
      uuid: 'req-1', requirementKey: 'solvent_a', consumeNodeUuid: 'node-9', targetType: 'reagent_info',
      reagentInfoUuid: undefined, requiredQuantity: 10, quantityUnit: 'mL', allowSplit: false,
      description: undefined, materialSourceNodeUuid: 'node-2',
    }])
  })
})

describe('updateReagent / deleteReagent', () => {
  it('sends a PUT with the optimistic revision and carries meta_data back untouched', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ code: 0, data: { uuid: 'rg-1', revision: 3 } }))
    vi.stubGlobal('fetch', fetchMock)
    await updateReagent({ uuid: 'rg-1', quantity: 45, quantityUnit: 'mL', expectedRevision: 2, description: '盘点', metaData: { source_reagent_uuid: 'rg-0', dispense_command_id: 'cmd-9' } })
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/reagents/rg-1')
    expect(fetchMock.mock.calls[0][1]?.method).toBe('PUT')
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      quantity: 45, quantity_unit: 'mL', expected_revision: 2, description: '盘点',
      meta_data: { source_reagent_uuid: 'rg-0', dispense_command_id: 'cmd-9' },
    })
  })

  it.each([
    { name: '省略浓度字段以保留原值', patch: {}, expected: {} },
    { name: '显式 null 清空浓度及单位', patch: { concentrationValue: null, concentrationUnit: null }, expected: { concentration_value: null, concentration_unit: null } },
    { name: '发送新浓度及单位', patch: { concentrationValue: 95, concentrationUnit: '%' }, expected: { concentration_value: 95, concentration_unit: '%' } },
    { name: '保留零浓度', patch: { concentrationValue: 0, concentrationUnit: 'mol/L' }, expected: { concentration_value: 0, concentration_unit: 'mol/L' } },
    { name: '单独更新浓度而不重写单位', patch: { concentrationValue: 10 }, expected: { concentration_value: 10 } },
    { name: '单独更新单位而不重写浓度', patch: { concentrationUnit: 'mmol/L' }, expected: { concentration_unit: 'mmol/L' } },
  ])('$name', async ({ patch, expected }) => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ code: 0, data: { uuid: 'rg-1', revision: 3 } }))
    vi.stubGlobal('fetch', fetchMock)
    await updateReagent({ uuid: 'rg-1', quantity: 45, quantityUnit: 'mL', expectedRevision: 2, ...patch })
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body)) as Record<string, unknown>
    expect(Object.fromEntries(Object.entries(body).filter(([key]) => key.startsWith('concentration_')))).toEqual(expected)
  })

  it('issues a DELETE for the reagent record', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ code: 0 }))
    vi.stubGlobal('fetch', fetchMock)
    await deleteReagent('rg-1')
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/reagents/rg-1')
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE')
  })
})
