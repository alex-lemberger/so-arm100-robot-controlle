/**
 * Feetech STS/SCS TTL packet helpers.
 *
 * STS3215 uses a half-duplex serial bus with packets of the form:
 * FF FF ID LENGTH INSTRUCTION PARAMS... CHECKSUM
 */

export const FEETECH = {
  header: [0xff, 0xff],
  broadcastId: 0xfe,
  instruction: {
    ping: 0x01,
    read: 0x02,
    write: 0x03,
    syncWrite: 0x83,
  },
  register: {
    torqueEnable: 40,
    goalPosition: 42,
    presentPosition: 56,
  },
} as const;

export interface FeetechPacket {
  id: number;
  instruction: number;
  parameters: Uint8Array;
  raw: Uint8Array;
}

const clampByte = (value: number) => Math.max(0, Math.min(0xff, Math.round(value)));
const clampWord = (value: number) => Math.max(0, Math.min(0xffff, Math.round(value)));

const checksumFor = (id: number, length: number, instruction: number, parameters: Uint8Array) => {
  let sum = id + length + instruction;
  for (const parameter of parameters) sum += parameter;
  return (~sum) & 0xff;
};

export function buildFeetechPacket(id: number, instruction: number, parameters: number[] | Uint8Array = []): Uint8Array {
  const safeId = clampByte(id);
  const body = Uint8Array.from(parameters, clampByte);
  const length = body.length + 2;
  const packet = new Uint8Array(body.length + 6);

  packet.set(FEETECH.header, 0);
  packet[2] = safeId;
  packet[3] = length;
  packet[4] = clampByte(instruction);
  packet.set(body, 5);
  packet[packet.length - 1] = checksumFor(safeId, length, packet[4], body);
  return packet;
}

export const buildPingPacket = (id: number) => buildFeetechPacket(id, FEETECH.instruction.ping);

export const buildReadPacket = (id: number, address: number, length: number) => (
  buildFeetechPacket(id, FEETECH.instruction.read, [address, length])
);

export const buildWritePacket = (id: number, address: number, data: number[] | Uint8Array) => (
  buildFeetechPacket(id, FEETECH.instruction.write, [address, ...data])
);

/**
 * Creates a SYNC_WRITE packet for the Goal_Position, Goal_Time and Goal_Speed
 * registers. This packet does not request replies and therefore is appropriate
 * only after the bus has been verified separately with PING/READ packets.
 */
export function buildSyncGoalPositionPacket(
  targets: Array<{ id: number; position: number }>,
  durationMs: number,
  speed = 0,
): Uint8Array {
  const duration = clampWord(durationMs);
  const safeSpeed = clampWord(speed);
  const parameters = [FEETECH.register.goalPosition, 6];

  for (const target of targets) {
    const position = Math.max(0, Math.min(4095, Math.round(target.position)));
    parameters.push(
      clampByte(target.id),
      position & 0xff,
      (position >> 8) & 0xff,
      duration & 0xff,
      (duration >> 8) & 0xff,
      safeSpeed & 0xff,
      (safeSpeed >> 8) & 0xff,
    );
  }

  return buildFeetechPacket(FEETECH.broadcastId, FEETECH.instruction.syncWrite, parameters);
}

export function parseFeetechPackets(input: Uint8Array): { packets: FeetechPacket[]; remainder: Uint8Array } {
  const packets: FeetechPacket[] = [];
  let offset = 0;

  while (offset + 4 <= input.length) {
    if (input[offset] !== 0xff || input[offset + 1] !== 0xff) {
      offset += 1;
      continue;
    }

    const length = input[offset + 3];
    const packetLength = length + 4;
    if (length < 2) {
      offset += 2;
      continue;
    }
    if (offset + packetLength > input.length) break;

    const raw = input.slice(offset, offset + packetLength);
    const id = raw[2];
    const instruction = raw[4];
    const parameters = raw.slice(5, raw.length - 1);
    const expectedChecksum = checksumFor(id, length, instruction, parameters);

    if (raw[raw.length - 1] === expectedChecksum) {
      packets.push({ id, instruction, parameters, raw });
      offset += packetLength;
    } else {
      // Preserve the second FF as a potential header for the next packet.
      offset += 1;
    }
  }

  return { packets, remainder: input.slice(offset) };
}

export const bytesToHex = (bytes: Uint8Array) => Array.from(bytes, value => value.toString(16).padStart(2, '0')).join(' ').toUpperCase();
